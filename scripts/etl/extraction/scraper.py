from scripts.utility.log import get_logger
from selenium import webdriver
from selenium_stealth import stealth
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support import expected_conditions as EC

import os
from time import sleep


logger = get_logger(__name__)


class BlockedError(RuntimeError):
    """O site respondeu com um desafio anti-bot (ex.: Cloudflare). Não insistir."""


BLOCK_MARKERS = ("Just a moment", "Attention Required")


class WebScraper:
    def __init__(self):
        self.driver = self.config_driver()

    def get_driver(self, url):
        self.driver.get(url)

    def config_driver(self) -> webdriver:
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("start-maximized")
        options.add_argument('--disable-gpu')
        options.add_argument("--disable-application-cache")
        options.add_argument("--disable-cache")
        options.add_argument("--incognito")
        options.add_experimental_option(
            "excludeSwitches",
            ["enable-automation"]
        )
        options.add_experimental_option('useAutomationExtension', False)

        # options.add_argument("--disable-dev-shm-usage")
        # options.add_argument("--no-sandbox")
        # options.add_argument("--remote-debugging-port=9222")

        # Driver fixo na imagem Docker (CHROMEDRIVER_PATH); fallback baixa via manager
        driver_path = os.getenv("CHROMEDRIVER_PATH") or ChromeDriverManager().install()
        driver = webdriver.Chrome(
            service=Service(driver_path),
            options=options
        )

        stealth(
            driver,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True
        )

        return driver

    def scroll_until_element_stops_moving(
            self,
            css_selector: str,
    ):
        previous_location = None
        attempts = 0

        element = WebDriverWait(self.driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, css_selector))
        )

        while attempts < 10:
            location = element.location_once_scrolled_into_view

            if previous_location is not None and location == previous_location:
                logger.info("The element has stopped moving.")
                break

            self.driver.execute_script(
                "arguments[0].scrollIntoView();",
                element
            )
            sleep(5)

            previous_location = location
            attempts += 1
            logger.info(f"Element moved to {location}")

    def get_elements(
        self,
        by: By,
        path: str,
        driver_element: webdriver = None
    ) -> webdriver:
        try:
            if driver_element:
                elements = WebDriverWait(driver_element, 10).until(
                    EC.presence_of_all_elements_located((by, path))
                )
            else:
                elements = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_all_elements_located((by, path))
                )
        except TimeoutException:
            return None

        return elements

    def get_element(
        self,
        by: By,
        path: str,
        attribute_type: str = None,
        driver_element: webdriver = None,
        timeout=10
    ) -> webdriver:
        try:
            if driver_element:
                element = WebDriverWait(driver_element, timeout).until(
                    EC.presence_of_element_located((by, path))
                )
            else:
                element = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((by, path))
                )
            sleep(1)
            if attribute_type == "text":
                return element.text
            elif attribute_type == "href":
                return element.get_attribute("href")
            elif attribute_type == "title":
                return element.get_attribute("title")
            elif attribute_type == "srcset":
                return element.get_attribute("srcset")
            elif attribute_type == "button":
                element.click()
        except TimeoutException:
            return None

        return element

    def fetch_html(self, url: str, wait_css: str, timeout: int = 20) -> str:
        """Abre a URL, espera o seletor aparecer e devolve o HTML renderizado."""
        self.driver.get(url)
        WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, wait_css))
        )
        return self.driver.page_source

    @staticmethod
    def fetch_html_once(
        url: str, wait_css: str, timeout: int = 20, retries: int = 2
    ) -> str:
        """Busca o HTML com um navegador novo; tenta de novo se expirar."""
        for attempt in range(1, retries + 1):
            scraper = WebScraper()
            try:
                return scraper.fetch_html(url, wait_css, timeout)
            except TimeoutException:
                try:
                    title = scraper.driver.title
                except Exception:
                    title = ""
                if any(marker in title for marker in BLOCK_MARKERS):
                    # Repetir logo em seguida só aumentaria a pressão sobre o site
                    raise BlockedError(f"desafio anti-bot: {title!r}") from None
                if attempt == retries:
                    raise
                sleep(5)
            finally:
                scraper.close_driver()

    def close_driver(self):
        self.driver.quit()

    def change_last_page(self):
        windows = self.driver.window_handles
        self.driver.switch_to.window(windows[-1])
