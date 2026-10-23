from app import news


def test_parsers():
    g = [{"items": [{"datetime": "202610232248", "officeName": "YTN", "officeId": "052", "articleId": "1", "title": "t", "titleFull": "코스피 &amp; 반등",
                     "body": "<b>본문</b>", "mobileNewsUrl": "https://n.news.naver.com/mnews/article/052/1"}]}]
    assert news.parse_naver_stock(g) == [{"time": "2026-10-23 22:48", "source": "YTN", "title": "코스피 & 반등", "summary": "본문",
                                          "url": "https://n.news.naver.com/mnews/article/052/1"}]
    m = news.parse_naver_main([{"dt": "20261023224110", "ohnm": "한경", "tit": "제목", "subcontent": "요약", "oid": "016", "aid": "9"}])
    assert m[0]["time"] == "2026-10-23 22:41" and m[0]["url"].endswith("/016/9")
    xml = ("<rss><channel><item><title>Nvidia falls - Barron&apos;s</title><link>https://news.google.com/x</link>"
           "<pubDate>Fri, 23 Oct 2026 13:11:00 GMT</pubDate><source url=\"https://barrons.com\">Barron's</source></item></channel></rss>")
    assert news.parse_google(xml) == [{"time": "2026-10-23 22:11", "source": "Barron's", "title": "Nvidia falls", "summary": "", "url": "https://news.google.com/x"}]
