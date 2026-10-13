# coding=utf-8
"""
燃超影院 aarnadhya.com | TVBox Python 爬虫 (lxml 版)
DOM 解析：
  - 卡片 a.zj-item，标题 @title，封面 img@src，状态 .zj-corner
  - 详情 .zj-detail-cover img、.zj-meta、.zj-desc、.zj-eps[data-sid] a.zj-ep
  - 播放 player_aaaa 内嵌 url 直链
"""
import re
import sys
import json
import time
import urllib.parse

sys.path.append('..')

try:
    from base.spider import Spider
except ImportError:
    import requests as _rq
    try:
        import urllib3
        urllib3.disable_warnings()
    except Exception:
        pass

    class _BaseSpider:
        def __init__(self):
            self._session = None

        @property
        def _sess(self):
            if self._session is None:
                self._session = _rq.Session()
                self._session.verify = False
                adapter = _rq.adapters.HTTPAdapter(
                    pool_connections=10, pool_maxsize=10, max_retries=0)
                self._session.mount('https://', adapter)
                self._session.mount('http://', adapter)
            return self._session

        def fetch(self, url, headers=None, **kw):
            timeout = kw.pop('timeout', 15)
            r = self._sess.get(url, headers=headers, timeout=timeout, **kw)
            r.encoding = 'utf-8'
            return r

        def log(self, *a, **kw):
            try:
                print("[rancho]", *a)
            except Exception:
                pass

    Spider = _BaseSpider

try:
    from lxml import etree
    HAS_LXML = True
except ImportError:
    HAS_LXML = False


HOST = "https://www.aarnadhya.com"
UA = ("Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36")
DEFAULT_PIC = HOST + "/template/m4-drama/images/favicon.svg"

CLASSES = [
    {"type_id": "1",  "type_name": "电影"},
    {"type_id": "2",  "type_name": "电视剧"},
    {"type_id": "3",  "type_name": "短剧"},
    {"type_id": "4",  "type_name": "动漫"},
    {"type_id": "5",  "type_name": "综艺"},
    {"type_id": "48", "type_name": "网飞新剧"},
    {"type_id": "47", "type_name": "AI漫剧"},
]

_GENRE_MAP = {
    "1":  ["剧情", "喜剧", "动作", "恐怖", "爱情", "科幻", "惊悚",
           "战争", "犯罪", "悬疑", "奇幻"],
    "2":  ["喜剧", "爱情", "悬疑", "古装", "剧情", "武侠", "都市",
           "仙侠", "谍战", "战争", "奇幻", "冒险"],
    "3":  ["现代都市", "女频恋爱", "古装仙侠", "反转爽剧", "穿越", "逆袭",
           "脑洞悬疑", "甜宠", "重生", "虐恋", "现代言情", "神豪", "悬疑"],
    "4":  ["剧情", "奇幻", "犯罪", "悬疑", "惊悚", "喜剧", "古装",
           "爱情", "科幻", "动作"],
    "5":  ["古装", "剧情", "喜剧", "动作", "都市", "爱情", "穿越", "科幻",
           "逆袭", "惊悚", "悬疑", "犯罪", "武侠", "谍战", "冒险"],
    "48": ["古装", "剧情", "喜剧", "动作", "都市", "爱情", "穿越", "科幻",
           "逆袭", "惊悚", "悬疑", "犯罪", "武侠", "谍战", "冒险"],
    "47": ["剧情", "奇幻", "犯罪", "悬疑", "惊悚", "喜剧", "古装",
           "爱情", "科幻", "动作"],
}

_AREAS = ["大陆", "香港", "台湾", "美国", "韩国", "日本", "欧美", "英国",
          "法国", "泰国", "印度", "加拿大", "西班牙", "德国", "俄罗斯", "新加坡"]
_YEARS = [str(y) for y in range(2026, 2011, -1)]
_SORTS = [("time", "最近更新"), ("hits", "最多播放"), ("score", "最高评分")]


def _mk(vals):
    out = [{"n": "全部", "v": ""}]
    for v in vals:
        out.append({"n": v, "v": v})
    return out


FILTERS = {}
for c in CLASSES:
    tid = c["type_id"]
    FILTERS[tid] = [
        {"key": "class", "name": "剧情",
         "value": _mk(_GENRE_MAP.get(tid, []))},
        {"key": "area", "name": "地区", "value": _mk(_AREAS)},
        {"key": "year", "name": "年份", "value": _mk(_YEARS)},
        {"key": "by",   "name": "排序",
         "value": [{"n": n, "v": v} for v, n in _SORTS]},
    ]


_RE_PLAYER = re.compile(r'var\s+player_aaaa\s*=\s*(\{[\s\S]*?\})\s*</script>', re.I)
_RE_PLAYER_URL = re.compile(r'"url"\s*:\s*"([^"]+)"', re.I)


class Spider(Spider):

    def getName(self):
        return "燃超影院"

    def init(self, extend=""):
        try:
            self.extend = json.loads(extend) if extend else {}
        except Exception:
            self.extend = {}

        self.site_url = (self.extend.get("site") or HOST).rstrip("/")
        self.headers = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Referer": self.site_url + "/",
        }
        self.default_pic = DEFAULT_PIC
        self._play_cache = {}
        self.log("init: site=%s lxml=%s" % (self.site_url, HAS_LXML))

    def _fetch(self, url, timeout=20, headers=None):
        try:
            h = dict(self.headers)
            h["Referer"] = url
            if headers:
                h.update(headers)
            rsp = self.fetch(url, headers=h, timeout=timeout)
            if hasattr(rsp, "text"):
                return rsp.text or ""
            if hasattr(rsp, "content"):
                return rsp.content.decode("utf-8", "ignore")
            return str(rsp)
        except Exception as e:
            self.log("fetch FAIL %s -> %s" % (url, e))
            return ""

    def _fix_url(self, url):
        if not url:
            return ""
        url = url.strip()
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("http"):
            return url
        if url.startswith("/"):
            return self.site_url + url
        return urllib.parse.urljoin(self.site_url + "/", url)

    def _clean(self, s):
        if not s:
            return ""
        s = (s.replace("&nbsp;", " ").replace("\xa0", " ")
              .replace("&amp;", "&").replace("&quot;", '"'))
        return re.sub(r"\s+", " ", s).strip()

    # ---------- lxml 卡片解析 ----------
    def _extract_videos(self, html):
        videos = []
        if not html or not HAS_LXML:
            return videos
        try:
            tree = etree.HTML(html)
        except Exception:
            return videos

        # a.zj-item —— 首页、分类页、搜索页结构一致
        nodes = tree.xpath('//a[contains(@class,"zj-item")]')
        seen = set()
        for a in nodes:
            href = a.get("href") or ""
            if not href.startswith("/video/"):
                continue
            if href in seen:
                continue
            seen.add(href)

            name = a.get("title") or ""
            if not name:
                t = a.xpath('.//div[contains(@class,"zj-item-title")]/text()')
                if t:
                    name = self._clean(t[0])

            pic = ""
            imgs = a.xpath('.//img/@src')
            if imgs:
                pic = self._fix_url(imgs[0])

            remark = ""
            corners = a.xpath('.//div[contains(@class,"zj-corner")]/@title')
            if corners:
                remark = self._clean(corners[0])

            videos.append({
                "vod_id":      href,
                "vod_name":    name[:100],
                "vod_pic":     pic or self.default_pic,
                "vod_remarks": remark,
            })
        return videos

    def _page_count(self, html, current_page=1):
        if not html or not HAS_LXML:
            return current_page
        try:
            tree = etree.HTML(html)
        except Exception:
            return current_page
        nums = tree.xpath('//nav[contains(@class,"zj-page")]//a/@href')
        mx = current_page
        for h in nums:
            m = re.search(r'/page/(\d+)', h)
            if m:
                try:
                    mx = max(mx, int(m.group(1)))
                except Exception:
                    pass
        if mx > current_page:
            return mx
        spans = tree.xpath('//nav[contains(@class,"zj-page")]//span/text()')
        for s in spans:
            m = re.search(r'\d+/(\d+)', s)
            if m:
                try:
                    return int(m.group(1))
                except Exception:
                    pass
        return current_page

    # ---------- TVBox 接口 ----------
    def homeContent(self, filter=False):
        return {"class": CLASSES, "filters": FILTERS}

    def homeVideoContent(self):
        html = self._fetch(self.site_url + "/")
        return {"list": self._extract_videos(html)}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg) if pg else 1
        except Exception:
            page = 1

        if isinstance(extend, str):
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        if not extend:
            extend = {}

        for k in list(extend.keys()):
            if extend[k] in ("", None, "全部"):
                del extend[k]

        seg = []
        if extend.get("class"):
            seg.append("class/%s" % urllib.parse.quote(extend["class"]))
        if extend.get("area"):
            seg.append("area/%s" % urllib.parse.quote(extend["area"]))
        if extend.get("lang"):
            seg.append("lang/%s" % urllib.parse.quote(extend["lang"]))
        if page > 1:
            seg.append("page/%d" % page)
        if extend.get("year"):
            seg.append("year/%s" % extend["year"])
        if extend.get("by"):
            seg.append("by/%s" % extend["by"])

        if seg:
            url = "%s/tv/%s/%s.html" % (self.site_url, tid, "/".join(seg))
        else:
            url = "%s/tv/%s.html" % (self.site_url, tid)

        self.log("category: %s" % url)
        html = self._fetch(url)
        self.log("  html len=%d" % len(html))
        videos = self._extract_videos(html)
        pc = self._page_count(html, page)
        self.log("  -> %d 条, 共 %d 页" % (len(videos), pc))
        return {
            "list": videos, "page": page, "pagecount": pc,
            "limit": 36, "total": pc * 36,
        }

    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg) if pg else 1
        except Exception:
            page = 1
        url = "%s/search.html?wd=%s" % (self.site_url, urllib.parse.quote(key))
        if page > 1:
            url += "&page=%d" % page
        self.log("search: %s" % url)
        html = self._fetch(url)
        videos = self._extract_videos(html)
        return {
            "list": videos, "page": page,
            "pagecount": self._page_count(html, page),
            "limit": 36, "total": 999,
        }

    def searchContentPage(self, key, quick, pg="1"):
        return self.searchContent(key, quick, pg)

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vod_id = str(ids[0])
        url = vod_id if vod_id.startswith("http") else self._fix_url(vod_id)
        self.log("detail: %s" % url)
        html = self._fetch(url)
        if not html or not HAS_LXML:
            return {"list": []}

        try:
            tree = etree.HTML(html)
        except Exception:
            return {"list": []}

        # 标题
        h1 = tree.xpath('//div[contains(@class,"zj-detail-info")]//h1//text()')
        name = ""
        if h1:
            name = self._clean(h1[0])
        if not name:
            t = tree.xpath('//title/text()')
            if t:
                name = self._clean(t[0].split("_")[0].split("-")[0])
        name = name or vod_id

        # 封面
        pic = self.default_pic
        imgs = tree.xpath('//div[contains(@class,"zj-detail-cover")]//img/@src')
        if imgs:
            pic = self._fix_url(imgs[0])

        # 导演 / 主演
        director, actor = "", ""
        metas = tree.xpath('//div[contains(@class,"zj-detail-info")]//span[contains(@class,"zj-meta-item")]')
        for s in metas:
            txt = "".join(s.itertext()).strip()
            if txt.startswith("导演："):
                director = self._clean(txt.replace("导演：", ""))
            elif txt.startswith("主演："):
                actor = self._clean(txt.replace("主演：", ""))

        # 评分
        score = ""
        sc = tree.xpath('//span[contains(@class,"zj-rating-num")]/text()')
        if sc:
            score = self._clean(sc[0])

        # 简介
        content = ""
        desc = tree.xpath('//p[contains(@class,"zj-desc")]//text()')
        if desc:
            content = self._clean("".join(desc))
        if not content:
            md = tree.xpath('//meta[@name="description"]/@content')
            if md:
                content = self._clean(md[0])
        content = ("🍊小橙子提醒您：请勿相信视频中的广告！\n" + content) if content \
            else "🍊小橙子提醒您：请勿相信视频中的广告！"

        # 线路名
        line_names = {}
        for b in tree.xpath('//button[contains(@class,"zj-line-btn")]'):
            sid = b.get("data-sid") or ""
            if sid:
                line_names[sid] = self._clean(b.text_content() if hasattr(b, "text_content") else "".join(b.itertext())) or ("线路%s" % sid)

        # 剧集面板
        groups = {}
        for panel in tree.xpath('//div[contains(@class,"zj-eps-panel")]'):
            sid = panel.get("data-sid") or ""
            if not sid:
                continue
            eps = []
            for a in panel.xpath('.//a[contains(@class,"zj-ep")]'):
                href = a.get("href") or ""
                if not href:
                    continue
                if href.startswith("/"):
                    href = self.site_url + href
                title = a.get("title") or "".join(a.itertext())
                title = self._clean(title)
                eps.append((title or ("第%d集" % (len(eps) + 1)), href))
            if eps:
                groups[sid] = eps

        self.log("  剧集线路: %s" % {k: len(v) for k, v in groups.items()})
        if not groups:
            return {"list": []}

        order = list(line_names.keys())
        for sid in groups.keys():
            if sid not in order:
                order.append(sid)

        play_from, play_url = [], []
        for sid in order:
            if sid not in groups:
                continue
            play_from.append(line_names.get(sid, "线路%s" % sid))
            play_url.append("#".join("%s$%s" % (n, h) for n, h in groups[sid]))

        return {"list": [{
            "vod_id":       vod_id,
            "vod_name":     name,
            "vod_pic":      pic,
            "vod_content":  content,
            "vod_actor":    actor,
            "vod_director": director,
            "vod_score":    score,
            "vod_remarks":  "%d条线路" % len(play_from),
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url":  "$$$".join(play_url),
        }]}

    def playerContent(self, flag, id, vipFlags):
        play_page = id if id.startswith("http") else self._fix_url(id)
        self.log("player: %s" % play_page)

        now = int(time.time())
        if play_page in self._play_cache:
            ts, res = self._play_cache[play_page]
            if now - ts < 600:
                return res

        html = self._fetch(play_page)
        real_url = ""
        if html:
            pm = _RE_PLAYER.search(html)
            if pm:
                um = _RE_PLAYER_URL.search(pm.group(1))
                if um:
                    real_url = um.group(1).replace("\\/", "/").replace("&amp;", "&")

        if real_url:
            self.log("  player url: %s" % real_url[:160])
            res = {"parse": 0, "playUrl": "", "url": real_url,
                   "header": {"User-Agent": UA, "Referer": self.site_url + "/"}}
        else:
            self.log("  未找到 player_aaaa，交给 TVBox 嗅探")
            res = {"parse": 1, "playUrl": "", "url": play_page,
                   "header": {"User-Agent": UA, "Referer": self.site_url + "/"}}
        self._play_cache[play_page] = (now, res)
        return res

    def isVideoFormat(self, url):
        return ".m3u8" in url or ".mp4" in url

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def close(self):
        self.destroy()
