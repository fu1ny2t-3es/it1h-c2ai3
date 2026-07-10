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

import logging
import os
import signal
import sys
from time import sleep
from typing import List

import pycron
from fire import Fire
from requests.exceptions import ReadTimeout

from . import DiskManager, __version__
from .ItchGame import ItchGame
from .ItchUser import ItchUser
from .web import generate_web
from .CfWrapper import CfWrapper

import json
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import datetime
from requests.exceptions import SSLError


# pylint: disable=missing-class-docstring
class ItchClaim:
    def __init__(self,
                version: bool = False,
                login: str = None,
                password: str = None,
                totp: str = None,
                flaresolverr_log_level: str = 'ERROR',
                flaresolverr_max_timeout: int = 900):
        """Automatically claim free games from itch.io

        Args:
            username (str): The username or email address of the user
            password (str): The password of the user
            totp (str): The 2FA code of the user
                Either the 6 digit code, or the secret used to generate the code
            flaresolverr_log_level (str): The logging level of FlareSolverr
                Default is 'ERROR'. Other options are: 'DEBUG', 'INFO', 'WARNING'
            flaresolverr_max_timeout (int): The maximum timeout for FlareSolverr in seconds
                Default is 120
        """

        # Set up FlareSolverr logging
        logging.getLogger("flaresolverr").setLevel(flaresolverr_log_level)
        flaresolverr_logger = logging.getLogger("flaresolverr")
        flaresolverr_logger.setLevel(flaresolverr_log_level)
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(flaresolverr_log_level)
        flaresolverr_logger.addHandler(ch)
        
        # CfWrapper is a singleton, so this sets the max timeout for all instances
        CfWrapper().max_timeout = flaresolverr_max_timeout

        if version:
            self.version()
        # Try loading username from environment variables if not provided as command line argument
        if login is None and os.getenv('ITCH_USERNAME') is not None:
            login = os.getenv('ITCH_USERNAME')
        if login is not None:
            self.login(login, password, totp)
        else:
            self.user = None

    def version(self):
        """Display the version of the script and exit"""
        print(__version__)
        exit(0)

    def refresh_sale_cache(
            self,
            games_dir: str = 'web/data/',
            sales: List[int] = None,
            max_pages: int = -1,
            no_fail: bool = False,
            max_not_found_pages: int = 25,
        ):
        """Refresh the cache about game sales
        Opens itch.io and downloads sales posted after the last saved one.

        Args:
            games_dir (str): Output directory
            sales: (List[int]): Only refresh the sales specified in this list
            max_pages (int): The maximum number of pages to download.
                Default is -1, which means unlimited
            no_fail (bool): Continue downloading sales even if a page fails to load
            max_not_found_pages (int): the maximum number of consecutive pages that return
                404 before stopping the execution. Default is 25"""
        resume = 1
        ItchGame.games_dir = games_dir
        os.makedirs(games_dir, exist_ok=True)

        if sales:
            print('--sales flag found - refreshing only select sale pages')
            for sale_id in sales:
                DiskManager.get_one_sale(sale_id)
            return

        try:
            with open(os.path.join(games_dir, 'resume_index.txt'), 'r', encoding='utf-8') as f:
                resume = int(f.read())
                print(f'Resuming sale downloads from {resume}')
        except FileNotFoundError:
            print('Resume index not found. Downloading sales from beginning')

        DiskManager.get_all_sales(
            resume,
            max_pages=max_pages,
            no_fail=no_fail,
            max_not_found_pages=max_not_found_pages
        )

        print('Updating games from sale lists, to catch updates of already known sales.')

        for category in ['games', 'tools', 'game-assets', 'comics', 'books', 'physical-games',
                'soundtracks', 'game-mods', 'misc']:
            print(f'Collecting sales from {category} list')
            DiskManager.get_all_sale_pages(category=category, no_fail=no_fail)

    def refresh_library(self):
        """Refresh the list of owned games of an account. This is used to skip claiming already
        owned games. Requires login."""
        if self.user is None:
            print('You must be logged in')
            return
        self.user.reload_owned_games()
        self.user.save_session()

    def claim(self, url: str = 'https://itchclaim.tmbpeter.com/api/active.json'):
        """Claim all unowned games. Requires login.
        Args:
            url (str): The URL to download the file from"""

        if self.user is None:
            print('You must be logged in')
            return
        if len(self.user.owned_games) == 0:
            print('User\'s library not found in cache. Downloading it now')
            self.user.reload_owned_games()
            self.user.save_session()

        print(f'Downloading free games list from {url}')
        games = DiskManager.download_from_remote_cache(url)

        print('Claiming games')
        claimed_games = 0
        for game in games:
            if not self.user.owns_game(game) and game.claimable:
                self.user.claim_game(game)
                self.user.save_session()
                claimed_games += 1
        if claimed_games == 0:
            print('No new games can be claimed.')

    def schedule(self, cron: str, url: str = 'https://itchclaim.tmbpeter.com/api/active.json'):
        """Start an infinite process of the script that claims games at a given schedule.
        Args:
            cron (str): The cron schedule to claim games
                See crontab.guru for syntax
            url (str): The URL to download the file from"""
        print(f'Starting cron job with schedule {cron}')

        # Define the signal handler
        def signal_handler(signum, frame):
            print("Interrupt signal received. Exiting...")
            exit(0)

        # Register the signal handler
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Start the scheduler
        while True:
            if not pycron.is_now(cron):
                sleep(60)
                continue
            self.claim(url)
            sleep(60)
        

    def download_urls(self, game_url: int):
        """Get details about a game, including it's CDN download URLs.

        Args:
            game_url (int): The url of the requested game."""
        game: ItchGame = ItchGame.from_api(game_url)
        session = self.user.s if self.user is not None else None
        print(game.downloadable_files(session))

    def generate_web(self, web_dir: str = 'web'):
        """Generates files that can be served as a static website
        
        Args:
            web_dir (str): Output directory"""

        ItchGame.games_dir = os.path.join(web_dir, 'data')
        os.makedirs(os.path.join(web_dir, 'api'), exist_ok=True)
        os.makedirs(ItchGame.games_dir, exist_ok=True)

        games = DiskManager.load_all_games()
        generate_web(games, web_dir)

    def recheck_unknown_claimability(self, games_dir: str = 'web/data/'):
        """Recheck games with unknown claimability"""

        ItchGame.games_dir = games_dir
        games = DiskManager.load_all_games()

        for game in games:
            if "claimable" not in game.__dict__ and game.active_sale:
                print(f'Rechecking claimability of {game.name} ({game.id})')
                try:
                    print(f'Found claimable: {game.claimable} for {game.name} (ID {game.id})')
                except ReadTimeout as e:
                    print(f'Timeout while checking claimability of {game.name} (ID {game.id}): {e}')
                    continue
                game.save_to_disk()

    def login(self,
                username: str = None,
                password: str = None,
                totp: str = None) -> ItchUser:
        """Load session from disk if exists, or use password otherwise.

        Args:
            username (str): The username or email address of the user
            password (str): The password of the user
            totp (str): The 2FA code of the user
                Either the 6 digit code, or the secret used to generate the code
        
        Returns:
            ItchUser: a logged in ItchUser instance
        """

        if not isinstance(username, str):
            username = input('Enter username: ')

        self.user = ItchUser(username)
        try:
            self.user.load_session()
            print(f'Session {username} loaded successfully')

            if not self.user.validate_session():
                print('Session is invalid or expired. Logging in again.')
                raise FileNotFoundError()
        except FileNotFoundError:
            # Try loading password from environment variables if not provided as command line argument
            if password is None:
                password = os.getenv('ITCH_PASSWORD')
            # Try loading TOTP from environment variables if not provided as command line argument
            if totp is None:
                totp = os.getenv('ITCH_TOTP')
            self.user.login(password, totp)
            print(f'Logged in as {username}')


    def _send_web(self, type: str, url: str, redirect = True, payload = None):
        timer = 10
        sleep_time = 10
        verify_ssl = True

        count = 0
        while True:
            if count >= (5 * 60 * 1000):  # 5 min * 60 sec * 1000 ms
                exit(0)

            count += 50 + sleep_time

            try:
                if type == 'get':
                    r = requests.get(url, data=payload, timeout=timer, allow_redirects=redirect, verify=verify_ssl)
                if type == 'post':
                    r = requests.post(url, data=payload, timeout=timer, allow_redirects=redirect, verify=verify_ssl)


                if type == 'user_get':
                    r = self.user.s.get(url, data=payload, timeout=timer, allow_redirects=redirect, verify=verify_ssl)
                if type == 'user_post':
                    r = self.user.s.post(url, data=payload, timeout=timer, allow_redirects=redirect, verify=verify_ssl)


                r.encoding = 'utf-8'

                if r.status_code == 200:  # OK
                    break

                if r.status_code == 301:  # Redirect permanent
                    break

                if r.status_code == 302:  # Redirect temporary
                    break

                if r.status_code == 403:  # Forbidden
                    break

                if r.status_code == 404:  # Not found
                    break

                if r.status_code == 451:  # Illegal content
                    break


                if (count % 100) == 0:
                    print(r.status_code, flush=True);

                sleep(sleep_time/1000.0)
            
            except SSLError as err:
                print(f"SSL Error: {err}", flush=True)
                verify_ssl=False

            except requests.RequestException as err:
                print(err, flush=True)
                sleep(sleep_time/1000.0)
                # pass

        return r


    def _claim(self, url):
        try:
            while True:
                r = self._send_web('user_post', url)

                if r.headers["content-type"].strip().startswith("application/json"):
                    break


            download_url = json.loads(r.text)
            if 'url' not in download_url:
                return

            download_url = download_url['url']
            r = self._send_web('user_get', download_url)

            soup = BeautifulSoup(r.text, 'html.parser')

            claim_box = soup.find('div', class_='claim_to_download_box warning_box')
            if claim_box == None:
                return

            claim_url = claim_box.find('form')
            if claim_url == None:
                return

            claim_url = claim_url['action']
            if claim_url == None:
                return

            r = self._send_web('user_post', claim_url, True, {'csrf_token': self.user.s.csrf_token})

        except Exception as err:
            print('[_claim] Failure while checking ' + url + ' = ' + str(err), flush=True)


    def _claim_reward(self, url):
        try:
            while True:
                r = self._send_web('get', url + '/data.json')
                
                if r.headers["content-type"].strip().startswith("application/json"):
                    break


            dat = json.loads(r.text)


            if 'rewards' not in dat:
                return


            for item in dat['rewards']:
                # print(item, flush=True)

                idx = 0
                while item['price'][idx].isdigit() == False:
                    idx += 1


                if item['price'][idx:] != '0.00':
                    continue

                if item['available'] != True:
                    continue

                self._claim(url + '/download_url?csrf_token=' + self.user.s.csrf_token + '&reward_id=' + str(item['id']))

        except Exception as err:
            print('[_claim_reward] Failure while checking ' + url + ' = ' + str(err), flush=True)


    def claim(self):
        with open('miss.txt', 'r') as myfile:
            for url in myfile.read().splitlines():
                self._claim_reward(url)
                self._claim(url + '/download_url?csrf_token=' + self.user.s.csrf_token)


    def rating(self):
        rated_games = set()


        print('Reviews', flush=True)
        url = 'https://itch.io/library/rated?json'

        page_num = 1
        try:
            while True:
                # print(url, flush=True)

                while True:
                    r = self._send_web('user_get', url)

                    if r.status_code == 404:
                        return -1

                    if r.headers["content-type"].strip().startswith("application/json"):
                        break


                dat = json.loads(r.text)

                if 'game_ratings' not in dat:
                    break

                extra = 0
                for item in dat['game_ratings']:
                    # print(item, flush=True)
                    rated_games.add(item['game']['id'])
                    extra += 1

                # print('Reviews page #' + str(page_num) + ': added ' + str(extra) + ' games (total: ' + str(len(rated_games)) + ')', flush=True)

                if 'next_page' not in dat:
                    break

                next_url = str(dat['next_page']).replace("'", '"')
                url = 'https://itch.io/library/rated?json&next_page=' + next_url
                page_num += 1

        except Exception as err:
            print('Failure to get reviews ' + url + ' = ' + str(err), flush=True)


        print('Things to rate', flush=True)
        url = 'https://itch.io/library/things-to-rate?json'

        page_num = 1
        try:
            while True:
                # print(url, flush=True)

                while True:
                    r = self._send_web('user_get', url)

                    if r.status_code == 404:
                        return -1

                    if r.headers["content-type"].strip().startswith("application/json"):
                        break


                dat = json.loads(r.text)

                if 'games' not in dat:
                    break

                extra = 0
                for item in dat['games']:
                    try:
                        game_id = item['id']
                        game_url = item['url']

                        if game_id in rated_games:
                            continue

                        print('Rating ' + game_url, flush=True)
                        rated_games.add(game_id)

                        data = {
                            'csrf_token': self.user.s.csrf_token,
                            'game_rating': '5'
                        }

                        r = self._send_web('user_post', game_url + '/rate?source=game&game_id=' + str(game_id), True, data)
                        if 'errors' in r.text:
                            continue

                        # print(r.text)
                        # print('Success!', flush=True)
                        # return

                    except Exception as err:
                        print('Failure to rate ' + game_url + ' = ' + str(err), flush=True)

                    # print(item, flush=True)
                    rated_games.add(item['id'])
                    extra += 1

                # print('Things to rate page #' + str(page_num) + ': added ' + str(extra) + ' games (total: ' + str(len(rated_games)) + ')', flush=True)

                if 'next_page' not in dat:
                    break

                next_url = str(dat['next_page']).replace("'", '"')
                url = 'https://itch.io/library/things-to-rate?json&next_page=' + next_url
                page_num += 1

        except Exception as err:
            print('Failure to get things to rate ' + url + ' = ' + str(err), flush=True)


        print('Owned', flush=True)
        page = 1

        while True:
            # print(f"owned page {page}", flush=True);

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
                game_id = item['game_id']
                game_url = item['game']['url']

                try:
                    if game_id in rated_games:
                        continue

                    print('Rating ' + game_url, flush=True)
                    rated_games.add(game_id)

                    data = {
                        'csrf_token': self.user.s.csrf_token,
                        'game_rating': '5'
                    }

                    r = self._send_web('user_post', game_url + '/rate?source=game&game_id=' + str(game_id), True, data)
                    if 'errors' in r.text:
                        continue

                    # print(r.text)
                    # print('Success!', flush=True)
                    # return

                except Exception as err:
                    print('Failure to rate ' + game_url + ' = ' + str(err), flush=True)

            page += 1


    def login(self,
                username: str = None,
                password: str = None,
                totp: str = None) -> ItchUser:
        """Load session from disk if exists, or use password otherwise.

        Args:
            username (str): The username or email address of the user
            password (str): The password of the user
            totp (str): The 2FA code of the user
                Either the 6 digit code, or the secret used to generate the code
        
        Returns:
            ItchUser: a logged in ItchUser instance
        """

        if not isinstance(username, str):
            username = input('Enter username: ')

        self.user = ItchUser(username)

        # Try loading password from environment variables if not provided as command line argument
        if password is None:
            password = os.getenv('ITCH_PASSWORD')
        # Try loading TOTP from environment variables if not provided as command line argument
        if totp is None:
            totp = os.getenv('ITCH_TOTP')
        self.user.login(password, totp)
        print(f'Logged in as {username}')


    def __init__(self,
                version: bool = False,
                login: str = None,
                password: str = None,
                totp: str = None,
                api_token: str = None,
                flaresolverr_log_level: str = 'ERROR',
                flaresolverr_max_timeout: int = 120):
        """Automatically claim free games from itch.io

        Args:
            username (str): The username or email address of the user
            password (str): The password of the user
            totp (str): The 2FA code of the user
                Either the 6 digit code, or the secret used to generate the code
            flaresolverr_log_level (str): The logging level of FlareSolverr
                Default is 'ERROR'. Other options are: 'DEBUG', 'INFO', 'WARNING'
            flaresolverr_max_timeout (int): The maximum timeout for FlareSolverr in seconds
                Default is 120
        """

        # Set up FlareSolverr logging
        logging.getLogger("flaresolverr").setLevel(flaresolverr_log_level)
        flaresolverr_logger = logging.getLogger("flaresolverr")
        flaresolverr_logger.setLevel(flaresolverr_log_level)
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(flaresolverr_log_level)
        flaresolverr_logger.addHandler(ch)
        
        # CfWrapper is a singleton, so this sets the max timeout for all instances
        CfWrapper().max_timeout = flaresolverr_max_timeout

        if version:
            self.version()
        # Try loading username from environment variables if not provided as command line argument
        if login is None and os.getenv('ITCH_USERNAME') is not None:
            login = os.getenv('ITCH_USERNAME')
        if login is not None:
            self.login(login, password, totp)
        else:
            self.user = None
        self.api_token = api_token


# pylint: disable=missing-function-docstring
def main():
    Fire(ItchClaim)
