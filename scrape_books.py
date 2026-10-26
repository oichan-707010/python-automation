"""books.toscrape.com から書籍のタイトル・価格・在庫状況を収集し、Markdownに保存する。"""

import logging
import random
import sys
import time
from dataclasses import dataclass
from datetime import date
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://books.toscrape.com/"
USER_AGENT = "python-automation-book-scraper/1.0"
TIMEOUT = 10
WAIT_RANGE = (1.0, 3.0)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("scrape_books.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


@dataclass
class Book:
    title: str
    price: str
    availability: str


def fetch(session: requests.Session, url: str) -> requests.Response:
    """URLを取得する。接続エラーやHTTPエラーの場合はログを出力して終了する。"""
    try:
        response = session.get(url, timeout=TIMEOUT)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error("接続エラーが発生しました: %s (%s)", url, e)
        sys.exit(1)
    response.encoding = "utf-8"
    return response


def load_robots(session: requests.Session) -> RobotFileParser:
    """robots.txt を読み込む。存在しない場合(4xx)はすべてのパスを許可する。"""
    robots_url = urljoin(BASE_URL, "robots.txt")
    parser = RobotFileParser(robots_url)
    try:
        response = session.get(robots_url, timeout=TIMEOUT)
    except requests.exceptions.RequestException as e:
        logger.error("接続エラーが発生しました: %s (%s)", robots_url, e)
        sys.exit(1)

    if response.status_code == 200:
        parser.parse(response.text.splitlines())
        logger.info("robots.txt を読み込みました")
    elif 400 <= response.status_code < 500:
        parser.allow_all = True
        logger.info("robots.txt が存在しないため、すべてのパスを許可します (HTTP %d)", response.status_code)
    else:
        # サーバーエラー時はアクセス可否が不明なため、すべて禁止として扱う
        parser.disallow_all = True
        logger.warning("robots.txt を取得できないため、アクセスを中止します (HTTP %d)", response.status_code)
    return parser


def parse_books(soup: BeautifulSoup) -> list[Book]:
    books = []
    for article in soup.select("article.product_pod"):
        books.append(
            Book(
                title=article.h3.a["title"],
                price=article.select_one("p.price_color").get_text(strip=True),
                availability=article.select_one("p.availability").get_text(strip=True),
            )
        )
    return books


def scrape(session: requests.Session, robots: RobotFileParser) -> list[Book]:
    books: list[Book] = []
    url: str | None = BASE_URL
    first = True

    while url:
        if not robots.can_fetch(USER_AGENT, url):
            logger.warning("robots.txt で禁止されているためスキップします: %s", url)
            break

        if not first:
            time.sleep(random.uniform(*WAIT_RANGE))
        first = False

        logger.info("取得中: %s", url)
        soup = BeautifulSoup(fetch(session, url).text, "html.parser")
        books.extend(parse_books(soup))

        next_link = soup.select_one("li.next > a")
        url = urljoin(url, next_link["href"]) if next_link else None

    return books


def escape_md(text: str) -> str:
    return text.replace("|", "\\|")


def save_markdown(books: list[Book], today: date) -> str:
    filename = f"books_{today.isoformat()}.md"
    lines = [
        f"# 書籍一覧 ({today.isoformat()})",
        "",
        f"- 取得元: {BASE_URL}",
        f"- 件数: {len(books)}",
        "",
        "| No. | タイトル | 価格 | 在庫状況 |",
        "| ---: | --- | ---: | --- |",
    ]
    for i, book in enumerate(books, start=1):
        lines.append(f"| {i} | {escape_md(book.title)} | {book.price} | {book.availability} |")

    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return filename


def main() -> None:
    with requests.Session() as session:
        session.headers["User-Agent"] = USER_AGENT
        robots = load_robots(session)
        books = scrape(session, robots)

    filename = save_markdown(books, date.today())
    logger.info("%d 件の書籍を %s に保存しました", len(books), filename)


if __name__ == "__main__":
    main()
