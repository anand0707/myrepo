# Copyright 2015 Hewlett-Packard Development Company, L.P
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import helpers
from pages.sources import sourcespage

class TestSource(helpers.TestCase):

    def test_source(self):
        source_pg = sourcespage.SourcePage(self.driver, self.CONFIG)
        source_pg.click_on_sources_button()
        source_pg.create_new_package_source()
        source_pg.delete_package_source()
