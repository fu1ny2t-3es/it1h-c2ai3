# The MIT License (MIT)
#
# Copyright (c) 2022-2025 Péter Tombor.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import os
import signal
import time
from time import sleep
from typing import List

import pycron
from fire import Fire

import json
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import datetime
from requests.exceptions import SSLError
from urllib.parse import urlparse


class GameName:
    def __init__(self,
                url: str = None,
                name: str = None):
        self.name = name
        self.url = url



class ItchCustom:
    def __init__(self,
                version: bool = False,
                login: str = None,
                password: str = None,
                totp: str = None,
                flaresolverr_log_level: str = 'ERROR',
                api_token: str = None):
        self.s = requests.Session()
        self.user = None
        self.api_token = api_token



    def _login(self, reload = True):
        self.active_sales = set()  # hashed, faster lookup
        self.future_sales = set()
        self.owned_list = set()



    def _substr(self, str, idx0, pat1, pat2):
        idx1 = str.find(pat1, idx0)
        if idx1 == -1:
            return None, -1

        idx1 += len(pat1)
        idx2 = str.find(pat2, idx1)

        if idx2 == -1:
            return None, -1

        return str[idx1:idx2], idx1



    def _dump_log(self, filename: str, mylist):
        if len(mylist) == 0:
            return

        with open(filename, 'w') as myfile:
            for line in mylist:
                print(line, file=myfile)  # Python 3.x



    def _dump_line(self, filename: str, line: str):
        with open(filename, 'a') as myfile:
            print(line, file=myfile)  # Python 3.x
            myfile.close()



    def _send_web(self, type: str, url: str, redirect = True, payload = None):
        timer = 50
        sleep_time = 50
        verify_ssl = True

        start_time = time.time()


        count = 0
        while True:
            if time.time() >= start_time + 10 * 60:  # 10 minutes
                exit(-1)

            count += 1

            try:
                if type == 'get':
                    # r = self.s.get(url, timeout=timer, allow_redirects=redirect, verify=verify_ssl)
                    r = requests.get(url, timeout=timer, allow_redirects=redirect, verify=verify_ssl)

                elif type == 'cf_get':
                    headers = { 'User-Agent': self.cf_agent }
                    cookies = { 'cf_clearance': self.cf_token }
                    print(cookies)
                    print(headers)
                    r = requests.get(url, timeout=timer, headers=headers, cookies=cookies, allow_redirects=redirect, verify=verify_ssl)
                    print(r.status_code)


                r.encoding = 'utf-8'

                if r.status_code == 200:  # OK
                    break

                elif r.status_code == 301:  # Redirect permanent
                    break

                elif r.status_code == 302:  # Redirect temporary
                    break

                elif r.status_code == 403:  # Forbidden
                    break

                elif r.status_code == 404:  # Not found
                    break

                elif r.status_code == 451:  # Illegal content
                    break

                elif r.status_code == 522:  # Timeout
                    if (count % 5) == 0:
                        print(f"{r.status_code} - {url}", flush=True);
                    continue


                elif (count % 25) == 0:
                    print(f"{r.status_code} - {url}", flush=True);

                sleep(sleep_time/1000.0)
            
            except SSLError as err:
                print(f"SSL Error: {err}", flush=True)
                verify_ssl=False

            except requests.RequestException as err:
                print(err, flush=True)
                sleep(sleep_time/1000.0)
                # pass

        return r



    def _claim_reward(self, url):
        if url in self.checked_list:
            return

        self.valid_reward = False
        self.scrape_count += 1

        self.checked_list.add(url)


        try:
            while True:
                r = self._send_web('get', url + '/data.json')

                if r.status_code == 404:
                    return -1

                if r.headers["content-type"].strip().startswith("application/json"):
                    break


            dat = json.loads(r.text)
            
            
            if 'rewards' not in dat:
                print(url + '  #', flush=True)
                self.ignore_list.add(url)

                return


            for item in dat['rewards']:
                # print(item, flush=True)

                idx = 0
                while item['price'][idx].isdigit() == False:
                    idx += 1

                if item['price'][idx:] != '0.00':
                    continue


                # print(url, flush=True)
                self.valid_reward = True


                if item['available'] != True:
                    continue


                while True:
                    r = self._send_web('user_post', url + '/download_url?csrf_token=' + self.user.csrf_token + '&reward_id=' + str(item['id']))

                    if r.headers["content-type"].strip().startswith("application/json"):
                        break


                download_url = json.loads(r.text)['url']
                r = self._send_web('user_get', download_url)

                soup = BeautifulSoup(r.text, 'html.parser')
                claim_box = soup.find('div', class_='claim_to_download_box warning_box')
                if claim_box == None:
                    raise Exception("No claim box") 

                claim_url = claim_box.find('form')['action']
                r = self._send_web('user_post', claim_url, True, {'csrf_token': self.user.csrf_token})

                if r.url == 'https://itch.io/':
                    raise Exception(r.text)

                # self.user.owned_games.append(game)
                print(f"Successfully claimed {url}", flush=True)

                break


        except Exception as err:
            print('[_claim_reward] Failure while claiming ' + url + ' = ' + str(err), flush=True)


        if self.valid_reward == True:
            print(url, flush=True)
            self.active_list.add(url)

        else:
            print(url + '  #', flush=True)
            self.ignore_list.add(url)



    def _claim_game(self, url):
        try:
            while True:
                r = self._send_web('user_post', url + '/download_url?csrf_token=' + self.user.csrf_token)

                if r.status_code == 404:
                    return -1

                if r.headers["content-type"].strip().startswith("application/json"):
                    break


            r.encoding = 'utf-8'
            resp = json.loads(r.text)


            if 'errors' in resp:
                if resp['errors'][0] in ('invalid game', 'invalid user'):
                    if game.check_redirect_url():
                        self._claim_game(url)
                        return
                raise Exception(resp['errors'][0])


            download_url = json.loads(r.text)['url']
            r = self._send_web('user_get', download_url)

            r.encoding = 'utf-8'

            # if 'Nothing is available for download yet.' in r.text:
              #  raise Exception('Nothing is available for download yet.')


            # if 'jubblands' in download_url:
            #    print(r.text)


            soup = BeautifulSoup(r.text, 'html.parser')
            claim_box = soup.find('div', class_='claim_to_download_box warning_box')
            if claim_box == None:
                print(url, flush=True)  # Python 3.x
                self.miss_list.append(url)

                self._dump_line('sale-miss.txt', url)
                #with open('itch-miss.txt', 'a') as myfile:
                #    print(url, file=myfile)  # Python 3.x
                return


            claim_url = claim_box.find('form')['action']
            r = self._send_web('user_post', claim_url, True, {'csrf_token': self.user.csrf_token})

            r.encoding = 'utf-8'
            if r.url == 'https://itch.io/':
                if 'promotion is no longer active' in r.text:
                    raise Exception('promotion is no longer active')
                else:
                    raise Exception(r.text)

            else:
                # self.owned_list.add(game)
                print(f"Successfully claimed {url}", flush=True)

        except Exception as err:
            print(f"ERROR: Failed to claim {url} = " + str(err), flush=True)



    def _claim_free(self, url: str = 'https://itchclaim.tmbpeter.com/api/active.json'):
        """Claim all unowned games. Requires login.
        Args:
            url (str): The URL to download the file from"""

        print(f'Downloading free games list from {url}', flush=True)
        games = DiskManager.download_from_remote_cache(url)

        print('Claiming games', flush=True)
        for game in games:
            for owned_url in [owned_game.url for owned_game in self.user.owned_games]:
                if owned_url == game.url:
                    break

            if owned_url == game.url:
                continue

            if game.url in self.miss_list:
                continue

            if game.url in self.future_list:
                continue

            if not self.user.owns_game(game):
                self._claim_game(game)



    def _claim_all(self, url: str = 'https://itchclaim.tmbpeter.com/api/all.json'):
        """Claim all unowned games. Requires login.
        Args:
            url (str): The URL to download the file from"""

        print(f'Downloading free games list from {url}', flush=True)
        games = DiskManager.download_from_remote_cache(url)

        print('Claiming games', flush=True)
        for game in games:
            for owned_url in [owned_game.url for owned_game in self.user.owned_games]:
                if owned_url == url:
                    continue

            if not self.user.owns_game(game):
                self._claim_game(game)



    def _check_reward(self, url):
        try:
            while True:
                r = self._send_web('get', url + '/data.json', False)
                
                if (r.status_code == 301) or (r.status_code == 302):
                    r = self._send_web('get', url, False)
                    url = r.headers["Location"]

                    if url in self.checked_list:
                        return
                    continue

                if r.status_code == 404:
                    return -1

                if r.headers["content-type"].strip().startswith("application/json"):
                    break


            dat = json.loads(r.text)


            if 'rewards' in dat:
                for item in dat['rewards']:
                    # print(item, flush=True)

                    idx = 0
                    while item['price'][idx].isdigit() == False:
                        idx += 1

                    if item['price'][idx:] != '0.00':
                        continue


                    r = self._send_web('get', url + '/purchase')
                    if r.status_code == 404:
                        return


                    self.valid_reward = True
                    self.active_list.add(url)

                    if item['available'] != True:
                        continue


                    print(url, flush=True)
                    self.miss_list.add(url)

                    return

        except Exception as err:
            print('[_check_reward] Failure while checking ' + url + ' = ' + str(err), flush=True)


        # print(url + '  #', flush=True)
        self.ignore_list.add(url)



    def _check_claim(self, url):
        try:
            r = self._send_web('get', url)

            if r.status_code == 404:
                return

            elif 'Download or claim' in r.text:
                print(url, flush=True)
                self.miss_list.add(url)
                self.valid_reward = True

        except Exception as err:
            print('[_check_claim] Failure while checking ' + url + ' = ' + str(err), flush=True)



    def _scrape_profile(self, url, main = True):
        self.checked_list.add(url)

        try:
#            if main == True:
#                self.profile_list.add(url)


            if self.scrape_count >= self.scrape_limit:
                if main == True:
                    self.profile_new.add(url)
                return


            # print(url, flush=True)

#            if main == True:
#                self.checked_list.add(url)

#            else:
#                url = (self._substr(url, 0, 'https://', '.itch.io'))[0]
#                url = 'https://itch.io/profile/' + url
#                self.checked_list.add(url)

            r = self._send_web('get', url)

            if r.status_code == 404:
                return -1


            str_index = 0
            while True:
                str1 = r.text.find('class="game_cell has_cover lazy_images"', str_index)
                if str1 == -1:
                    break
                str_index = str1+1


#                game = ItchGame(-1)
#                game.url = (self._substr(r.text, str1, 'href="', '"'))[0]

                new_url = (self._substr(r.text, str1, 'href="', '"'))[0]
                new_author = (self._substr(new_url, 0, 'https://', '.itch.io'))[0]
                new_profile = 'https://' + new_author + '.itch.io'


                if new_url in self.checked_list:
                    continue


                self.profile_new.add(new_profile)


                # print(new_url + '  ?')
                self._check_reward(new_url)
                self._check_claim(new_url)


                if self.valid_reward == True:
                    self.profile_active.add(new_profile)
                    # print(new_url + '  ?')


                self.checked_list.add(new_url)


        except Exception as err:
            print('[_scrape_profile] Failure while checking ' + url + ' = ' + str(err), flush=True)



    def scrape_rewards(self):
        """Claim all unowned games. Requires login.
        Args:
            url (str): The URL to download the file from"""
            # https://www.google.com/search?q=%2B%22itch.io%22+%2B%22free+community+Copy%22
            # https://www.google.com/search?q=itch.io+%22community+copies%22


        self._login()


        self.ignore_list = set()  # faster hashing
        self.active_list = set()

        self.checked_list = set()

        self.profile_active = set()
        self.profile_ignore = set()
        self.profile_new = set()
        self.profile_list = set()

        self.valid_reward = False
        self.scrape_count = 0
        self.scrape_limit = 500
        # self.scrape_limit = 2000
        # self.scrape_limit = 9999999999



        myfile = open('ignore.txt', 'r')
        for game_url in myfile.read().splitlines():
            # print(game_url)
            self.ignore_list.add(game_url)
            self.checked_list.add(game_url)


        myfile = open('active.txt', 'r')
        for game_url in myfile.read().splitlines():
            if game_url in self.owned_list:
                continue
            if game_url in self.ignore_list:
                continue

            self.active_list.add(game_url)


        myfile = open('profiles.txt', 'r')
        for game_url in myfile.read().splitlines():
            self.profile_list.add(game_url)


        myfile = open('profiles-active.txt', 'r')
        for game_url in myfile.read().splitlines():
            self.profile_active.add(game_url)



        print(f'Checking active profiles ...', flush=True)
        print(datetime.now())

        active_list_old = set(self.profile_active)
        for new_profile in active_list_old:
            try:
                if new_profile not in self.checked_list:
                    # print(new_profile + '  #', flush=True)
                    self._scrape_profile(new_profile)

            except Exception as err:
                print('Failure while checking ' + profile_url + ' = ' + str(err), flush=True)



        print(f'Checking collections ...', flush=True)
        print(datetime.now())

        myfile = open('collections.txt', 'r')
        for page_url in myfile.read().splitlines():
            page = 1
            url = page_url + '?format=json'

            try:
                while True:
                    # print(url, flush=True)
                    r = self._send_web('get', url)
                    dat = json.loads(r.text)

                    if dat['num_items'] == 0:
                        break


                    str_index = 0
                    while True:
                        str1 = dat['content'].find('class="game_cell has_cover lazy_images"', str_index)
                        if str1 == -1:
                            break
                        str_index = str1+1

                        new_author = (self._substr(dat['content'], str1, 'href="https://', '.itch.io'))[0]
                        new_profile = 'https://' + new_author + '.itch.io'


                        if new_profile not in self.checked_list:
                            # print(new_profile, flush=True)
                            self._scrape_profile(new_profile)

                    page += 1
                    url = page_url + '?format=json&page=' + str(page)


            except Exception as err:
                print('[scrape_rewards] Failure while checking ' + url + ' = ' + str(err), flush=True)



        print(f'Checking owned collection ...', flush=True)
        print(datetime.now())

        owned_list_old = set(self.owned_list)
        for game_url in owned_list_old:
            try:
                new_author = (self._substr(game_url, 0, 'https://', '.itch.io'))[0]
                new_profile = 'https://' + new_author + '.itch.io'

                if new_profile not in self.checked_list:
                    # print(new_profile + '  o', flush=True)
                    self._scrape_profile(new_profile)

            except Exception as err:
                print('Failure while checking ' + profile_url + ' = ' + str(err), flush=True)



        print(f'Checking new profiles ...', flush=True)
        print(datetime.now())

        profile_list_old = set(self.profile_new)
        for new_profile in profile_list_old:
            try:
                if new_profile not in self.checked_list:
                    # print(new_profile, flush=True)
                    self._scrape_profile(new_profile)

            except Exception as err:
                print('Failure while checking ' + new_profile + ' = ' + str(err), flush=True)



        print(str(self.scrape_count) + ' / ' + str(self.scrape_limit))



        with open('active.txt', 'w') as myfile:
            for line in sorted(self.active_list):
                if line in self.ignore_list:
                    continue
                print(line, file=myfile)  # Python 3.x

        with open('ignore.txt', 'w') as myfile:
            for line in sorted(self.ignore_list):
                print(line, file=myfile)  # Python 3.x

        with open('profiles.txt', 'w') as myfile:
            for line in sorted(self.profile_list):
                print(line, file=myfile)  # Python 3.x

        with open('profiles-active.txt', 'w') as myfile:
            for line in sorted(self.profile_active):
                print(line, file=myfile)  # Python 3.x



    def scrape_rewards_other(self):
        """Check non-active profiles. Requires login.
        Args:
            url (str): The URL to download the file from"""
            # https://www.google.com/search?q=%2B%22itch.io%22+%2B%22free+community+Copy%22
            # https://www.google.com/search?q=itch.io+%22community+copies%22


        self._login()


        self.ignore_list = set()  # faster hashing
        self.active_list = set()

        self.profile_active = set()
        self.profile_ignore = set()
        self.profile_new = set()
        self.profile_list = set()

        self.checked_list = set()

        self.valid_reward = False
        self.scrape_count = 0
        self.scrape_limit = 750  # 500 = 4m, 1000 = 6m, [2000] = 13m, 2500 = 16m, 5000 ~ 32m
        # self.scrape_limit = 9999999999



        myfile = open('ignore.txt', 'r')
        for game_url in myfile.read().splitlines():
            # print(game_url)
            self.ignore_list.add(game_url)


        myfile = open('active.txt', 'r')
        for game_url in myfile.read().splitlines():
            if game_url in self.owned_list:
                continue

            self.active_list.add(game_url)


        myfile = open('profiles.txt', 'r')
        for game_url in myfile.read().splitlines():
            self.profile_list.add(game_url)


        myfile = open('profiles-active.txt', 'r')
        for game_url in myfile.read().splitlines():
            self.checked_list.add(game_url)



        print(f'Checking non-active profiles ...', flush=True)
        print(datetime.now())

        profile_list_old = set(self.profile_list)
        for new_profile in profile_list_old:
            try:
                if new_profile not in self.checked_list:
                    # print(new_profile, flush=True)
                    self._scrape_profile(new_profile)

            except Exception as err:
                print('Failure while checking ' + profile_url + ' = ' + str(err), flush=True)



        print(str(self.scrape_count) + ' / ' + str(self.scrape_limit))



        with open('active.txt', 'w') as myfile:
            for line in sorted(self.active_list):
                print(line, file=myfile)  # Python 3.x

        with open('ignore.txt', 'w') as myfile:
            for line in sorted(self.ignore_list):
                print(line, file=myfile)  # Python 3.x

        with open('profiles.txt', 'w') as myfile:
            for line in sorted(self.profile_list):
                print(line, file=myfile)  # Python 3.x

        with open('profiles-active.txt', 'w') as myfile:
            for line in sorted(self.profile_active):
                print(line, file=myfile)  # Python 3.x



    def active_profile(self):
        self.ignore_list = set()
        self.active_list = set()
        self.miss_list = set()
        self.scrape_list = set()

        self.checked_list = set()

        self.profile_active = set()
        self.profile_ignore = set()
        self.profile_new = set()
        self.profile_list = set()

        self.valid_reward = False
        self.scrape_limit = 10000000
        self.scrape_count = 0



        with open('owned-list.txt', 'r') as myfile:
            for url in myfile.read().splitlines():
                self.checked_list.add(url)
                self.profile_active.add(f"{urlparse(url).scheme}://{urlparse(url).netloc}")


        with open('profiles-active.txt', 'r') as myfile:
            for url in myfile.read().splitlines():
                self.scrape_list.add(url)
                self.profile_active.add(url)


        for url in self.scrape_list:
            try:
                if url not in self.checked_list:
                    self._scrape_profile(url)

            except Exception as err:
                print('Failure while checking ' + url + ' = ' + str(err), flush=True)


        print('Writing logs.txt')

        with open('miss.txt', 'w') as myfile:
            for url in sorted(self.miss_list):
                print(url, file=myfile)


        with open('profiles-active.txt', 'w') as myfile:
            for line in sorted(self.profile_active):
                print(line, file=myfile)  # Python 3.x

        return



        print('Writing ignore.txt')
        with open('ignore.txt', 'w') as myfile:
            for url in sorted(self.ignore_list):
                print(url, file=myfile)


        print('Writing active.txt')
        with open('active.txt', 'w') as myfile:
            for url in sorted(self.active_list):
                print(url, file=myfile)

        return



        myfile = open('profiles.txt', 'r')
        for game_url in myfile.read().splitlines():
            self.profile_list.add(game_url)


        myfile = open('profiles-active.txt', 'r')
        for game_url in myfile.read().splitlines():
            self.profile_active.add(game_url)



        print(f'Checking active profiles ...', flush=True)
        print(datetime.now())

        active_list_old = set(self.profile_active)
        for new_profile in active_list_old:
            try:
                if new_profile not in self.checked_list:
                    # print(new_profile + '  #', flush=True)
                    self._scrape_profile(new_profile)

            except Exception as err:
                print('Failure while checking ' + profile_url + ' = ' + str(err), flush=True)



        print(f'Checking collections ...', flush=True)
        print(datetime.now())

        myfile = open('collections.txt', 'r')
        for page_url in myfile.read().splitlines():
            page = 1
            url = page_url + '?format=json'

            try:
                while True:
                    # print(url, flush=True)
                    r = self._send_web('get', url)
                    dat = json.loads(r.text)

                    if dat['num_items'] == 0:
                        break


                    str_index = 0
                    while True:
                        str1 = dat['content'].find('class="game_cell has_cover lazy_images"', str_index)
                        if str1 == -1:
                            break
                        str_index = str1+1

                        new_author = (self._substr(dat['content'], str1, 'href="https://', '.itch.io'))[0]
                        new_profile = 'https://' + new_author + '.itch.io'


                        if new_profile not in self.checked_list:
                            # print(new_profile, flush=True)
                            self._scrape_profile(new_profile)

                    page += 1
                    url = page_url + '?format=json&page=' + str(page)


            except Exception as err:
                print('[scrape_rewards] Failure while checking ' + url + ' = ' + str(err), flush=True)



        print(f'Checking owned collection ...', flush=True)
        print(datetime.now())

        owned_list_old = set(self.owned_list)
        for game_url in owned_list_old:
            try:
                new_author = (self._substr(game_url, 0, 'https://', '.itch.io'))[0]
                new_profile = 'https://' + new_author + '.itch.io'

                if new_profile not in self.checked_list:
                    # print(new_profile + '  o', flush=True)
                    self._scrape_profile(new_profile)

            except Exception as err:
                print('Failure while checking ' + profile_url + ' = ' + str(err), flush=True)



        print(f'Checking new profiles ...', flush=True)
        print(datetime.now())

        profile_list_old = set(self.profile_new)
        for new_profile in profile_list_old:
            try:
                if new_profile not in self.checked_list:
                    # print(new_profile, flush=True)
                    self._scrape_profile(new_profile)

            except Exception as err:
                print('Failure while checking ' + new_profile + ' = ' + str(err), flush=True)



        print(str(self.scrape_count) + ' / ' + str(self.scrape_limit))



        with open('active.txt', 'w') as myfile:
            for line in sorted(self.active_list):
                if line in self.ignore_list:
                    continue
                print(line, file=myfile)  # Python 3.x

        with open('ignore.txt', 'w') as myfile:
            for line in sorted(self.ignore_list):
                print(line, file=myfile)  # Python 3.x

        with open('profiles.txt', 'w') as myfile:
            for line in sorted(self.profile_list):
                print(line, file=myfile)  # Python 3.x

        with open('profiles-active.txt', 'w') as myfile:
            for line in sorted(self.profile_active):
                print(line, file=myfile)  # Python 3.x



    def active_reward(self):
        self.owned_list = set()  # faster hashing
        self.ignore_list = set()
        self.active_list = set()
        self.miss_list = set()
        self.scrape_list = set()

        self.checked_list = set()

        self.profile_active = set()
        self.profile_ignore = set()
        self.profile_new = set()
        self.profile_list = set()

        self.valid_reward = False



        with open('owned-list.txt', 'r') as myfile:
            for url in myfile.read().splitlines():
                self.owned_list.add(url)


        with open('ignore.txt', 'r') as myfile:
            for url in myfile.read().splitlines():
                self.ignore_list.add(url)
                # self.checked_list.add(game_url)


        with open('active.txt', 'r') as myfile:
            for url in myfile.read().splitlines():
                self.scrape_list.add(url)
                # self.checked_list.add(game_url)


        for url in self.scrape_list:
            if url in self.owned_list:
                continue

            self._check_reward(url)


        print('Writing ignore.txt')
        with open('ignore.txt', 'w') as myfile:
            for url in sorted(self.ignore_list):
                print(url, file=myfile)


        print('Writing active.txt')
        with open('active.txt', 'w') as myfile:
            for url in sorted(self.active_list):
                print(url, file=myfile)


        print('Writing miss.txt')
        with open('miss.txt', 'w') as myfile:
            for url in sorted(self.miss_list):
                print(url, file=myfile)


        return



        myfile = open('profiles.txt', 'r')
        for game_url in myfile.read().splitlines():
            self.profile_list.add(game_url)


        myfile = open('profiles-active.txt', 'r')
        for game_url in myfile.read().splitlines():
            self.profile_active.add(game_url)



        print(f'Checking active profiles ...', flush=True)
        print(datetime.now())

        active_list_old = set(self.profile_active)
        for new_profile in active_list_old:
            try:
                if new_profile not in self.checked_list:
                    # print(new_profile + '  #', flush=True)
                    self._scrape_profile(new_profile)

            except Exception as err:
                print('Failure while checking ' + profile_url + ' = ' + str(err), flush=True)



        print(f'Checking collections ...', flush=True)
        print(datetime.now())

        myfile = open('collections.txt', 'r')
        for page_url in myfile.read().splitlines():
            page = 1
            url = page_url + '?format=json'

            try:
                while True:
                    # print(url, flush=True)
                    r = self._send_web('get', url)
                    dat = json.loads(r.text)

                    if dat['num_items'] == 0:
                        break


                    str_index = 0
                    while True:
                        str1 = dat['content'].find('class="game_cell has_cover lazy_images"', str_index)
                        if str1 == -1:
                            break
                        str_index = str1+1

                        new_author = (self._substr(dat['content'], str1, 'href="https://', '.itch.io'))[0]
                        new_profile = 'https://' + new_author + '.itch.io'


                        if new_profile not in self.checked_list:
                            # print(new_profile, flush=True)
                            self._scrape_profile(new_profile)

                    page += 1
                    url = page_url + '?format=json&page=' + str(page)


            except Exception as err:
                print('[scrape_rewards] Failure while checking ' + url + ' = ' + str(err), flush=True)



        print(f'Checking owned collection ...', flush=True)
        print(datetime.now())

        owned_list_old = set(self.owned_list)
        for game_url in owned_list_old:
            try:
                new_author = (self._substr(game_url, 0, 'https://', '.itch.io'))[0]
                new_profile = 'https://' + new_author + '.itch.io'

                if new_profile not in self.checked_list:
                    # print(new_profile + '  o', flush=True)
                    self._scrape_profile(new_profile)

            except Exception as err:
                print('Failure while checking ' + profile_url + ' = ' + str(err), flush=True)



        print(f'Checking new profiles ...', flush=True)
        print(datetime.now())

        profile_list_old = set(self.profile_new)
        for new_profile in profile_list_old:
            try:
                if new_profile not in self.checked_list:
                    # print(new_profile, flush=True)
                    self._scrape_profile(new_profile)

            except Exception as err:
                print('Failure while checking ' + new_profile + ' = ' + str(err), flush=True)



        print(str(self.scrape_count) + ' / ' + str(self.scrape_limit))



        with open('active.txt', 'w') as myfile:
            for line in sorted(self.active_list):
                if line in self.ignore_list:
                    continue
                print(line, file=myfile)  # Python 3.x

        with open('ignore.txt', 'w') as myfile:
            for line in sorted(self.ignore_list):
                print(line, file=myfile)  # Python 3.x

        with open('profiles.txt', 'w') as myfile:
            for line in sorted(self.profile_list):
                print(line, file=myfile)  # Python 3.x

        with open('profiles-active.txt', 'w') as myfile:
            for line in sorted(self.profile_active):
                print(line, file=myfile)  # Python 3.x



    def _scrape_sale_id(self, step, start, stop):
        scrape_list = set()
        checked_list = set()

        sale_list = set()

        old_item = list()
        new_item = list()

        download_item = list()
        future_item = list()
        claim_item = list()
        empty_item = list()

        scrape_page = 0


        with open('owned-list.txt', 'r') as myfile:
            for url in myfile.read().splitlines():
                checked_list.add(url)

        with open('sale-stop.txt', 'r') as myfile:
            scrape_page = int(myfile.read())

        with open('miss.txt', 'r') as myfile:
            for url in myfile.read().splitlines():
                old_item.append(url)


        scrape_page += start
        print(f'Scraping {scrape_page} ...', flush=True)


        with open('sale.txt', 'r') as myfile:
            for url in myfile.read().splitlines():
                scrape_list.add(url)


        page_count = 0
        count_404 = 0

        while True:
            try:
                if (step != 0) and (page_count >= stop):
                    break


                if len(scrape_list) > 0:
                    url = scrape_list.pop()
                    r = self._send_web('get', url)


                else:
                    url = f"https://itch.io/s/{scrape_page}"
                    r = self._send_web('get', url)


                    page_count += 1
                    scrape_page += step

                    if (scrape_page % 50) == 0:
                        print(scrape_page, flush=True)


                    if r.status_code == 404:  # No redirect = no sale created
                        # print('404 -- ' + url, flush=True)
                        count_404 += 1

                        if count_404 < 200:
                            continue

                        scrape_page -= 200
                        break

                    count_404 = 0

                if 'This sale ended' in r.text:
                    continue

                if '"percent_off">100%</strong> more' in r.text:
                    continue

                if '"percent_off">100%' not in r.text:
                    continue


                sale_url = url
                sale_list.add(sale_url)


                future_sale = False
                if 'class="not_active_notification">Come back' in r.text:
                    # print('Future sale', flush=True)
                    future_sale = True


                idx = 0
                once = 0

                while True:
                    idx = r.text.find('class="game_cell_data"', idx)
                    if idx == -1:
                        break
                    idx += 1


                    url = (self._substr(r.text, idx, 'href="', '"'))[0]

                    if url not in checked_list:
                        new_item.append(url)

                        if future_sale == True:
                            print(url + '    >>>  Future sale', flush=True)
                            future_item.append(url)

                        else:
                            r2 = self._send_web('get', url)

                            if r2.status_code == 404:
                                continue
                            elif '>Support This Game</a>' in r2.text:
                                print(url + '    ***  No download', flush=True)
                                empty_item.append(url)
                            elif 'Download or claim' in r2.text:
                                print(url + '    ###  Claim now', flush=True)
                                claim_item.append(url)
                            else:
                                print(url, flush=True)
                                download_item.append(url)

            except Exception as err:
                print('Failure while checking ' + url + ' = ' + str(err), flush=True)


        print('Writing logs.txt')

        if step == 1:
            with open("sale-stop.txt", 'w') as myfile:
                print(scrape_page, file=myfile)


        with open('sale.txt', 'w', encoding="utf-8") as myfile:
            for url in sorted(sale_list):
                print(url, file=myfile)


        with open('sale-log.txt', 'w', encoding="utf-8") as myfile:
            print('Claim:', file=myfile)
            for url in claim_item:
                print(url, file=myfile)

            print('', file=myfile)
            print('-----------', file=myfile)
            print('', file=myfile)

            print('Download:', file=myfile)
            for url in download_item:
                if url not in old_item:
                    print(url, file=myfile)

            old_item.reverse()
            for url in old_item:
                if url in download_item:
                    print(url, file=myfile)
            old_item.reverse()

            print('', file=myfile)
            print('-----------', file=myfile)
            print('', file=myfile)

            print('Future:', file=myfile)
            for url in future_item:
                print(url, file=myfile)


        with open('miss.txt', 'w', encoding="utf-8") as myfile:
            for url in old_item:
                if url in new_item:
                    print(url, file=myfile)

            for url in new_item:
                if url not in old_item:
                    print(url, file=myfile)



    def past_sale(self):
        self._scrape_sale_id(-1,0,2000)


    def future_sale(self):
        self._scrape_sale_id(1,-100,999999)



    def active_sale(self):
        owned_list = set()
        miss_list = set()


        with open('owned-list.txt', 'r') as myfile:
            for url in myfile.read().splitlines():
                owned_list.add(url)


        while True:
            try:
                r = self._send_web('get', 'https://itchclaim.tmbpeter.com/api/active.json')

                if r.status_code == 200 and r.headers["content-type"].strip().startswith("application/json"):  # OK
                    break

            except:
                pass

        r.encoding = 'utf-8'


        idx = 0
        while True:
            idx = r.text.find('"url":', idx)
            if idx == -1:
                break
            idx += len('"url":')


            url = (self._substr(r.text, idx, '"', '"'))[0]

            while (url not in owned_list) and (url not in miss_list):
                r2 = self._send_web('get', url, False)

                if 'Location' in r2.headers:
                    url = r2.headers['Location']
                    r2 = self._send_web('get', url, False)
                    continue

                if r2.status_code == 404:
                    break
                elif '>Support This Game</a>' in r2.text:
                    print(url + '    ***  No download', flush=True)
                elif '/purchase">Download or claim' in r2.text:
                    print(url + '    ###  Claim now', flush=True)
                else:
                    print(url, flush=True)

                miss_list.add(url)
                break



        with open('miss.txt', 'w', encoding="utf-8") as myfile:
            for game in sorted(miss_list):
                print(game, file=myfile)



    def owned(self):
        page = 1

        with open('owned-list.txt', 'w', encoding="utf-8") as myfile:
            while True:
                print(f"page {page}", flush=True);

                while True:
                    try:
                        # r = self.s.get(f"https://itch.io/my-purchases?page={page}&format=json", timeout=timer)
                        r = self._send_web('get', f"https://api.itch.io/profile/owned-keys?api_key={self.api_token}&page={page}")

                        if r.status_code == 200 and r.headers["content-type"].strip().startswith("application/json"):  # OK
                            break

                    except:
                        pass

                r.encoding = 'utf-8'


                if len(json.loads(r.text)['owned_keys']) == 0:
                    break


                for item in json.loads(r.text)['owned_keys']:
                    for type in item['game']:
                        if type == 'url':
                            game = ItchGame(item['game']['url'], item['game']['title'])
                            print(game.url, file=myfile)

                page += 1



    def sync(self):
        owned_list = list()
        master_list = set()
        removed_list = set()


        try:
            with open('owned-old.txt', 'r') as myfile:
                for url in myfile.read().splitlines():
                    if url not in master_list:
                        master_list.add(url)
        except:
            pass


        try:
            with open('removed.txt', 'r') as myfile:
                for url in myfile.read().splitlines():
                    if url not in removed_list:
                        removed_list.add(url)
        except:
            pass


        page = 1

        while True:
            print(f"page {page}", flush=True);

            while True:
                try:
                    # r = self.s.get(f"https://itch.io/my-purchases?page={page}&format=json", timeout=timer)
                    r = self._send_web('get', f"https://api.itch.io/profile/owned-keys?api_key={self.api_token}&page={page}")

                    if r.status_code == 200 and r.headers["content-type"].strip().startswith("application/json"):  # OK
                        break

                except:
                    pass

            r.encoding = 'utf-8'


            if len(json.loads(r.text)['owned_keys']) == 0:
                break


            for item in json.loads(r.text)['owned_keys']:
                for type in item['game']:
                    if type == 'url':
                        game = GameName(item['game']['url'], item['game']['title'])
                        owned_list.append(game)

                        if game.url not in master_list:
                            # print(game.url)
                            master_list.add(game.url)

            page += 1


        print('Creating owned.txt', flush=True)
        with open('owned.txt', 'w', encoding="utf-8") as myfile:
            for game in owned_list:
                print(f"{game.name:60s} {game.url:50s}", file=myfile)


        print('Creating removed.txt', flush=True)
        with open('removed.txt', 'w') as myfile:
            for game in sorted(master_list):
                if not any(item.url == game for item in owned_list):
                    if game not in removed_list:
                        r = self._send_web('get', game, False)

                    if 'Location' in r.headers:
                        master_list.remove(game)
                        continue

                    print(game, file=myfile)


        print('Creating owned-list.txt', flush=True)
        with open('owned-list.txt', 'w') as myfile:
            for game in sorted(owned_list, key=lambda x: x.url):
                print(game.url, file=myfile)


        print('Creating owned-author.txt', flush=True)
        with open('owned-author.txt', 'w', encoding="utf-8") as myfile:
            for game in sorted(owned_list, key=lambda x: x.url):
                print(f"{game.name:60s} {game.url:50s}", file=myfile)


        print('Creating owned-name.txt', flush=True)
        with open('owned-name.txt', 'w', encoding="utf-8") as myfile:
            for game in sorted(owned_list, key=lambda x: x.name):
                print(f"{game.name:60s} {game.url:50s}", file=myfile)


        print('Creating owned-old.txt', flush=True)
        with open('owned-old.txt', 'w') as myfile:
            for game in sorted(master_list):
                print(game, file=myfile)



# pylint: disable=missing-function-docstring
def main():
    old = datetime.now()

    Fire(ItchCustom)

    print(old)
    print(datetime.now())



if __name__ == "__main__":
    main()
