import re
from django.contrib.staticfiles.testing import StaticLiveServerTestCase

from selenium.webdriver.firefox.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from aasemble.django.tests import create_session_cookie


class RepositoryFunctionalTests(StaticLiveServerTestCase):
    # fixtures = ['data.json']

    @classmethod
    def setUpClass(cls):
        super(RepositoryFunctionalTests, cls).setUpClass()
        cls.selenium = WebDriver()
        cls.selenium.maximize_window()

    @classmethod
    def tearDownClass(cls):
        cls.selenium.quit()
        super(RepositoryFunctionalTests, cls).tearDownClass()

    def test_user_signs_up_for_signup(self):
        self.selenium.get('%s%s' % (self.live_server_url, '/accounts/signup/'))
        username_input = self.selenium.find_element_by_id('id_email')
        username_input.send_keys('newuser@linux2go.dk')
        password1_input = self.selenium.find_element_by_id('id_password1')
        password1_input.send_keys('secret')
        password2_input = self.selenium.find_element_by_id('id_password2')
        password2_input.send_keys('secret')
        signup_form = self.selenium.find_element_by_id('signup_form')
        signup_form.submit()
        page_header = self.selenium.find_element_by_class_name('page-header')
        text_found = re.search(r'Dashboard', page_header.text)
        self.assertNotEqual(text_found, None)

    def test_secured_pages_open_after_login(self):
        session_cookie = create_session_cookie(username='test@email.com', password='top_secret')
        self.selenium.get(self.live_server_url)
        self.selenium.add_cookie(session_cookie)

        # test whether sources page opens after user logs in
        self.selenium.get('%s%s' % (self.live_server_url, '/buildsvc/sources/'))
        page_header = self.selenium.find_element_by_class_name('page-header')
        text_found = re.search(r'Sources', page_header.text)
        self.assertNotEqual(text_found, None)

    def test_source_botton (self):
        self.test_user_signs_up_for_signup()
        self.click_on_sources_button()
        #self.create_new_package_source()
        #self.delete_package_source()
        
    def click_on_sources_button(self):
        try :
       #     if self.sources_button.is_displayed():
            self.sources_button.click()
                #print "source button found"
        except NoSuchElementException:
            print "source button not found" 

    @property
    def sources_button(self):
        return self.selenium.find_element(by.By.LINK_TEXT, 'Sources')