from instagrapi import Client
from instagrapi.exceptions import LoginRequired
from .logger_config import logger
from getpass import getpass
import requests
import os
from dotenv import load_dotenv

load_dotenv()

class InstagramClient:
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.client = Client()

    def login(self) -> None:
        if os.path.exists(os.path.join(os.getcwd(), "session.json")):
            session = self.client.load_settings(os.path.join(os.getcwd(), "session.json"))
        else:
            session = None

        login_via_session = False
        login_via_pw = False

        if session:
            try:
                self.client.set_settings(session)
                self.client.login(self.username, self.password)

                # check if session is valid
                try:
                    self.client.get_timeline_feed()
                except LoginRequired:
                    logger.warning("Session is invalid, need to login via username and password")

                    old_session = self.client.get_settings()

                    # use the same device uuids across logins
                    self.client.set_settings({})
                    self.client.set_uuids(old_session["uuids"])

                    self.client.login(self.username, self.password)
                login_via_session = True
            except Exception as e:
                logger.error("Couldn't login user using session information: %s" % e)

        if not login_via_session:
            try:
                logger.info("Attempting to login via username and password. username: %s" % self.username)
                if self.client.login(self.username, self.password):
                    login_via_pw = True
            except Exception as e:
                logger.error("Couldn't login user using username and password: %s" % e)

        if not login_via_pw and not login_via_session:
            raise Exception("Couldn't login user with either password or session")
        
        logger.info("Login successful")
        self.client.dump_settings(os.path.join(os.getcwd(), "session.json"))

    def fetch_reels(self, last_pk, count: int = 10) -> list[str]:
        if last_pk is None:
            last_pk = 0
        reels = self.client.reels_timeline_media("explore_reels", count, last_media_pk=last_pk)
        last_pk = reels[-1].pk if reels else last_pk
        return [reel.video_url for reel in reels if reel.video_url], last_pk


if __name__ == "__main__":
    username = os.getenv("IGUSERNAME")
    password = os.getenv("IGPASSWORD")
    client = InstagramClient(username, password)

    try:
        client.login()

        video_urls = client.fetch_reels(last_pk=0)
        print(f"Fetched {len(video_urls)} reels")
        for i, url in enumerate(video_urls, 1):
            print(f"{i}. {url}")
    except Exception as e:
        print(f"Error: {e}")