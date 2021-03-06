from glob import glob
import importlib
import logging
import os
import os.path
import shutil
import subprocess
import tempfile
import uuid
from six.moves.urllib.parse import urlparse

from django.conf import settings
from django.db import models
from django.forms import ModelForm
from django.contrib.auth import models as auth_models
from django.template.loader import render_to_string
from django.utils.encoding import python_2_unicode_compatible
from django.utils.module_loading import import_string

import deb822

from ...utils import run_cmd, recursive_render

from . import tasks

LOG = logging.getLogger(__name__)

def ensure_dir(d):
    if not os.path.isdir(d):
        os.makedirs(d)
    return d

def remove_ddebs_from_changes(changes_file):
    with open(changes_file, 'r') as fp:
        changes = deb822.Changes(fp)

    for section in ('Checksums-Sha1', 'Checksums-Sha256', 'Files'):
        if section not in changes:
            continue
        new_section = [f for f in changes[section] if not f['name'].endswith('.ddeb')]
        changes[section] = new_section

    with open(changes_file, 'w') as fp:
        fp.write(changes.dump())

class RepositoryDriver(object):
    def __init__(self, repository):
        self.repository = repository

class FakeDriver(RepositoryDriver):
    def generate_key(self):
        return 'FAKEID'

class RepreproDriver(RepositoryDriver):
    def generate_key(self):
        LOG.info('Generating key for %s' % (self.repository))
        gpg_input = render_to_string('buildsvc/gpg-keygen-input.tmpl',
                                     {'repository': self.repository})
        output = run_cmd(['gpg', '--batch', '--gen-key'], input=gpg_input)

        for l in output.split('\n'):
            if l.startswith('gpg: key '):
                return l.split(' ')[2]

def get_repo_driver(repository):
    driver_name = getattr(settings, 'BUILDSVC_REPODRIVER', 'aasemble.django.apps.buildsvc.models.RepreproDriver')
    driver = import_string(driver_name)
    return driver(repository)

@python_2_unicode_compatible
class Repository(models.Model):
    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(auth_models.User)
    name = models.CharField(max_length=100)
    key_id = models.CharField(max_length=100)
    extra_admins = models.ManyToManyField(auth_models.Group)

    class Meta:
        verbose_name_plural = 'repositories'
        unique_together = (('user', 'name'),)

    def __str__(self):
        return '%s/%s' % (self.user.username, self.name)

    @property
    def sources(self):
        return PackageSource.objects.filter(series__repository=self)

    @classmethod
    def lookup_by_user(cls, user):
        if not user.is_active:
            return cls.objects.none()
        if user.is_superuser:
            return cls.objects.all()
        return cls.objects.filter(user=user) | cls.objects.filter(extra_admins__in=user.groups.all())

    def ensure_key(self):
        if not self.key_id:
            self.key_id = get_repo_driver(self).generate_key()
            self.save()

    def first_series(self):
        return Series.objects.get_or_create(defaults={'name': settings.BUILDSVC_DEFAULT_SERIES_NAME}, repository=self)[0]

    @property
    def basedir(self):
        basedir = os.path.join(settings.BUILDSVC_REPOS_BASE_DIR, self.user.username, self.name)
        return ensure_dir(basedir)

    def confdir(self):
        return os.path.join(self.basedir, 'conf')

    def outdir(self):
        return os.path.join(settings.BUILDSVC_REPOS_BASE_PUBLIC_DIR,
                            self.user.username, self.name)

    @property
    def buildlogdir(self):
        return ensure_dir(os.path.join(self.outdir(), 'buildlogs'))

    def gpghome(self):
        return os.path.join(self.basedir, '.gnupg')

    def ensure_directory_structure(self):
        recursive_render(os.path.join(os.path.dirname(__file__),
                                      'templates/buildsvc/reprepro'),
                         self.basedir, {'repository': self})

    def _reprepro(self, *args):
        env = {'GNUPG_HOME': self.gpghome()}
        return run_cmd(['reprepro', '-b', self.basedir] + list(args),
                       override_env=env)

    def export_key(self):
        keypath = os.path.join(self.outdir(), 'repo.key')
        if not os.path.exists(keypath):
            output = run_cmd(['gpg', '-a', '--export', self.key_id])
            with open(keypath, 'w') as fp:
                fp.write(output)

    def export(self):
        self.ensure_key()
        self.ensure_directory_structure()
        self.export_key()
        self._reprepro('export')

    def process_changes(self, series_name, changes_file):
        self.ensure_directory_structure()
        remove_ddebs_from_changes(changes_file)
        self._reprepro('--ignore=wrongdistribution', 'include', series_name, changes_file)
        self.export()

    @property
    def base_url(self):
        return '%s/%s/%s' % (settings.BUILDSVC_REPOS_BASE_URL,
                             self.user.username,
                             self.name)


    def user_can_modify(self, user):
        if not user.is_active:
            return False
        if user == self.user or user.is_superuser:
            return True
        if self.extra_admins.filter(user=user).exists():
            return True
        return False


@python_2_unicode_compatible
class Series(models.Model):
    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    repository = models.ForeignKey(Repository, related_name='series')

    def __str__(self):
        return '%s/%s' % (self.repository.name, self.name)

    def binary_source_list(self, force_trusted=False):
        return self._source_list(prefix='deb', force_trusted=force_trusted)

    def source_source_list(self, force_trusted=False):
        return self._source_list(prefix='deb-src', force_trusted=force_trusted)

    def _source_list(self, prefix, force_trusted=False):
        if force_trusted:
            option = ' [trusted=yes]'
        else:
            option = ''
        return '%s%s %s %s main' % (prefix,
                                    option,
                                    self.repository.base_url,
                                    self.name)

    class Meta:
        verbose_name_plural = 'series'

    def process_changes(self, changes_file):
        self.repository.process_changes(self.name, changes_file)

    def export(self):
        self.repository.export()

    def user_can_modify(self, user):
        return self.repository.user_can_modify(user)


class ExternalDependency(models.Model):
    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    url = models.URLField()
    series = models.CharField(max_length=200)
    components = models.CharField(max_length=200, null=True, blank=True)
    own_series = models.ForeignKey(Series)
    key = models.TextField()

    @property
    def deb_line(self):
        return 'deb %s %s %s' % (self.url, self.series, self.components)

    def user_can_modify(self, user):
        return self.own_series.user_can_modify(user)


@python_2_unicode_compatible
class PackageSource(models.Model):
    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    git_url = models.URLField()
    branch = models.CharField(max_length=100)
    series = models.ForeignKey(Series, related_name='sources')
    last_seen_revision = models.CharField(max_length=64, null=True, blank=True)
    last_built_version = models.CharField(max_length=64, null=True, blank=True)
    last_built_name = models.CharField(max_length=64, null=True, blank=True)
    build_counter = models.IntegerField(default=0)

    def __str__(self):
        return '%s/%s' % (self.git_url, self.branch)

    def poll(self):
        cmd = ['git', 'ls-remote', self.git_url,
               'refs/heads/%s' % self.branch]
        stdout = run_cmd(cmd)
        sha = stdout.split('\t')[0]

        if sha == self.last_seen_revision:
            return False

        self.last_seen_revision = sha
        self.save()
        return True

    def checkout(self, sha=None, logger=LOG):
        tmpdir = tempfile.mkdtemp()
        builddir = os.path.join(tmpdir, 'build')
        try:
            run_cmd(['git',
                     'clone', self.git_url,
                     '-b', self.branch,
                     'build'],
                    cwd=tmpdir, logger=logger)

            if sha:
                run_cmd(['git', 'reset', '--hard', sha], cwd=builddir, logger=logger)

            stdout = run_cmd(['git', 'rev-parse', 'HEAD'], cwd=builddir, logger=logger)
            return tmpdir, builddir, stdout.strip()
        except:
            shutil.rmtree(tmpdir)
            raise

    @property
    def long_name(self):
        return '_'.join(filter(bool, urlparse(self.git_url).path.split('/')))

    @property
    def name(self):
        return self.git_url.split('/')[-1].replace('_', '-')

    def build(self):
        tasks.build.delay(self.id)

    def build_real(self):
        self.build_counter += 1
        self.save()

        br = BuildRecord(source=self, build_counter=self.build_counter)
        br.save()

        tmpdir, self.builddir, br.sha = self.checkout(logger=br.logger)
        br.save()
        try:
            import pkgbuild
            builder_cls = pkgbuild.choose_builder(self.builddir)
            builder = builder_cls(tmpdir, self, br)

            builder.build()

            changes_files = filter(lambda s:s.endswith('.changes'), os.listdir(tmpdir))

            for changes_file in changes_files:
                self.series.process_changes(os.path.join(tmpdir, changes_file))

            self.series.export()
        finally:
            shutil.rmtree(tmpdir)


    def delete_on_filesystem(self):
        if self.last_built_name:
            tasks.reprepro.delay(self.series.repository.id, 'removesrc', self.series.name, self.last_built_name)

    def user_can_modify(self, user):
        return self.series.user_can_modify(user)


class BuildRecord(models.Model):
    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey(PackageSource)
    version = models.CharField(max_length=50)
    build_counter = models.IntegerField(default=0)
    build_started = models.DateTimeField(auto_now_add=True)
    sha = models.CharField(max_length=100, null=True, blank=True)

    def __init__(self, *args, **kwargs):
        self._logger = None
        self._saved_logpath = None
        return super(BuildRecord, self).__init__(*args, **kwargs)

    @property
    def logger(self):
        logpath = self.buildlog()

        if not logpath == self._saved_logpath:
            LOG.debug('logpath changed from %r to %r' % (self._saved_logpath, logpath))

            # buildlog path changed, move it
            if self._saved_logpath and os.path.exists(self._saved_logpath):
                LOG.debug('Existing logfile found. Renaming')
                os.rename(self._saved_logpath, self.buildlog())

            logger = logging.getLogger('buildsvc.pkgbuild.%s_%s' % (self.source.name, self.build_counter))
            logger.setLevel(logging.DEBUG)

            for handler in logger.handlers:
                logger.removeHandler(handler)

            formatter = logging.Formatter('%(asctime)s: %(message)s')
            logfp = logging.FileHandler(logpath)
            logfp.setLevel(logging.DEBUG)
            logfp.setFormatter(formatter)

            logger.addHandler(logfp)
            self._logger = logger
            self._saved_logpath = logpath

        return self._logger

    def logpath(self):
        LOG.debug('Determining logpath for %s. version = %r' % (self, self.version))
        if self.version:
           return os.path.join(self.source.long_name, '%s_%s.log' % (self.source.long_name, self.version))
        else:
           return os.path.join(self.source.long_name, '%s_%s.tmp.log' % (self.source.long_name, self.build_counter))

    def buildlog(self):
        path = os.path.join(self.source.series.repository.buildlogdir,
                            self.logpath())

        dirpath = os.path.dirname(path)

        if not os.path.isdir(dirpath):
            os.makedirs(dirpath)

        return path

    def buildlog_url(self):
        return '%s/buildlogs/%s' % (self.source.series.repository.base_url,
                                    self.logpath())

@python_2_unicode_compatible
class GithubRepository(models.Model):
    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(auth_models.User)
    repo_owner = models.CharField(max_length=100)
    repo_name = models.CharField(max_length=100)

    def __str__(self):
        return self.url

    class Meta:
        verbose_name_plural = 'Github repositories'
        ordering = ['repo_owner', 'repo_name']
        unique_together = ('user', 'repo_owner', 'repo_name')

    @property
    def url(self):
        return 'https://github.com/%s/%s' % (self.repo_owner, self.repo_name)

    @classmethod
    def create_from_github_repo(cls, user, github_repo):
        obj = cls(user=user,
                  repo_owner=github_repo['owner']['login'],
                  repo_name=github_repo['name'])
        obj.save()
        return obj


class PackageSourceForm(ModelForm):
    class Meta:
        model = PackageSource
        fields = ['git_url', 'branch', 'series']
