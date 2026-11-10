"""Sense-label heuristics and sense ranking (source-agnostic)."""
from __future__ import annotations

import re

# Section headings that are never descriptors of the entity itself.
_GENERIC_EXACT = {
    "简介", "基本信息", "基本资料", "基本介绍", "基本简介", "基本概况", "基本解释",
    "基本释义", "基本参数", "基本内容", "基本相信", "词语", "词目", "词条", "概述",
    "概况", "概要", "摘要", "定义", "释义", "解释", "介绍", "信息", "资料", "目录",
    "百科名片", "百度名片", "名片", "历史", "沿革", "历史沿革", "发展史", "发展历史",
    "作者", "原料", "材料", "用料", "配料", "做法", "步骤", "制作方法", "重要参数",
    "主要参数", "参数", "规格", "特点", "特征", "作用", "功效", "用途", "原理",
    "内容", "意义", "影响", "来源", "出处", "拼音", "注音", "读音", "生平", "经历",
    "简历", "履历", "成就", "评价", "作品", "荣誉", "综述", "说明", "注释", "详解",
    "地理位置", "名称类别", "应用领域", "任期和要求", "参考文献", "相关", "其他",
    "其它", "备注", "正文", "词语信息", "词语解释", "汉语词语", "英文", "英语",
    "基本概念", "制作材料", "美食材料", "主要材料", "所需材料", "个人作品", "主要作品",
    "代表作品", "硬件设备", "商标品牌", "采用国家", "建桥技术", "基本情况", "基本概述",
    "人物简介", "人物经历", "人物生平", "个人经历", "个人简介", "个人资料", "个人档案",
    "工种名称", "菜谱名称", "菜谱口味", "所属地区", "所属类别", "产品类别", "产品介绍",
    "官方网站", "作者其他作品", "作者其它作品", "安全术语", "专业术语", "相关术语",
}
# Heading-like suffixes: "XX简介", "XX信息", "XX参数" …
_GENERIC_SUFFIX_RE = re.compile(
    r"(简介|介绍|信息|资料|参数|概述|概况|释义|解释|定义|名片|沿革|历史|背景|职责|职能|"
    r"用料|做法|步骤|特点|特征|分布|形态|作用|功效|用途|原理|内容|意义|影响|来源|出处|"
    r"词语|词目|词汇|词条|拼音|注音|读音|生平|经历|简历|履历|成就|评价|作品|荣誉|概要|"
    r"综述|说明|注释|详解|目录|材料|原料|配料|提示|详情|档案|明细|类别|领域|位置|要求|"
    r"参考|文献|相关|年表|大事记|列表|一览|表|图|版|篇|章|节|记|录|略|述|论|法|式|方)$"
)
# A descriptor names *what kind of thing* the entity is.  Require one of these
# entity-type words at the end (or a leading year) so that odd headings like
# 任期和要求 or 主板芯片 are not promoted to sense labels.
_DESCRIPTOR_SUFFIX_RE = re.compile(
    r"(词语|成语|词汇|术语|名词|动词|俚语|方言|俗语|谚语|歇后语|姓氏|汉字|"
    r"电影|电视剧|动画|动漫|漫画|小说|诗歌|诗词|散文|歌曲|专辑|单曲|游戏|软件|"
    r"书籍|图书|杂志|期刊|报纸|节目|综艺|戏剧|话剧|歌剧|舞剧|音乐剧|"
    r"演员|歌手|导演|编剧|作家|诗人|画家|书法家|艺术家|音乐家|作曲家|歌唱家|主持人|模特|"
    r"运动员|教练|球员|教授|学者|专家|医生|院士|研究员|工程师|设计师|建筑师|企业家|商人|"
    r"官员|将领|将军|皇帝|国王|王后|公主|王子|大臣|宰相|丞相|诸侯|皇后|太子|"
    r"局长|副局长|厅长|副厅长|处长|副处长|科长|市长|副市长|县长|副县长|省长|副省长|"
    r"书记|副书记|主任|副主任|部长|副部长|委员|常委|代表|主席|副主席|总裁|总经理|董事长|"
    r"校长|副校长|院长|副院长|所长|副所长|站长|馆长|队长|组长|厂长|经理|董事|"
    r"人物|人士|名人|烈士|英雄|劳模|博士|硕士|学生|教师|老师|讲师|法师|和尚|道士|神父|牧师|"
    r"公司|企业|银行|学校|大学|学院|中学|小学|医院|组织|协会|学会|基金会|政府|"
    r"车型|手机|电脑|相机|仪器|药品|药物|化合物|矿物|"
    r"植物|动物|昆虫|鸟类|鱼类|品种|物种|真菌|细菌|病毒|疾病|综合征|"
    r"地名|城市|县|区|镇|乡|村|街道|社区|岛|山|河|湖|海|湾|公园|景区|车站|机场|港口|"
    r"地区|省|州|朝代|王朝|民族|语言|宗教|"
    r"战争|战役|会议|比赛|赛事|联赛|奖项|称号|节日|习俗|菜品|美食|小吃|饮品|酒)$"
)
_LEADING_DIGIT_RE = re.compile(r"^\d")
# "主要景点", "特色景点", "所辖省区", "同名歌曲", "配合…": headings about the
# entity, not descriptors of it.
_GENERIC_PREFIX_RE = re.compile(
    r"^(主要|特色|具体|所辖|所属|设立|同名|配合|相关|其他|其它|各|该|本|此|常见|著名|知名|重要|典型|"
    r"现任|历任|曾|参演|主演|出演|演出|邻近|年度|下辖|所在|出品|发行|获得|所获|关于)")
_YEAR_PREFIX_RE = re.compile(r"^\d{4}年")
_PUNCT_RE = re.compile(r"[：:，,。、；;！!？?（）()《》【】\[\]\"“”'‘’·…—\-/\|]")


def is_descriptor(section_title: str | None, title: str) -> bool:
    """Decide whether a first-section heading reads as a sense descriptor
    (e.g. 李永赋 → 云南晋宁县公安局副局长) rather than a generic heading
    (简介 / 基本信息 / 词语 / XX参数)."""
    if not section_title:
        return False
    s = section_title.strip().rstrip("：:")
    if not s or s in _GENERIC_EXACT:
        return False
    if not (4 <= len(s) <= 24):
        return False
    if _PUNCT_RE.search(s):
        return False
    if _GENERIC_SUFFIX_RE.search(s) and not _DESCRIPTOR_SUFFIX_RE.search(s):
        return False
    t = title.strip()
    if t and (t in s or s in t):
        return False
    # heavy character overlap with the title → it is "<title> something"
    if t:
        overlap = len(set(s) & set(t)) / max(1, len(set(s)))
        if overlap > 0.5:
            return False
    if _YEAR_PREFIX_RE.match(s):
        return True
    if _LEADING_DIGIT_RE.match(s):  # "1明朝山水画家": a stray list number
        return False
    if _GENERIC_PREFIX_RE.match(s):
        return False
    return bool(_DESCRIPTOR_SUFFIX_RE.search(s))


# Subtitles that say the article is the word itself: 汉语词汇, 汉字, 成语, 词语解释
_WORD_LABEL_RE = re.compile(
    r"^(?:汉语|中文|现代汉语|古代汉语)?(?:常用|通用|一级|二级)?"
    r"(?:词语|词汇|汉字|成语|字词|文字|单字|熟语|俗语|惯用语|名词|动词|形容词|副词|量词|连词|介词|助词|代词|叹词|字)"
    r"(?:解释|释义)?$")
# Subtitles that name a work: 张学友演唱歌曲, 2021年上映的纪录电影, 张爱玲创作的小说
_WORK_LABEL_RE = re.compile(
    r"歌曲|单曲|专辑|插曲|主题曲|片尾曲|片头曲|电影|影片|电视剧|网剧|剧集|纪录片|动画|动漫|漫画|小说|图书|书籍|"
    r"著作|杂志|期刊|节目|综艺|游戏|话剧|歌剧|舞剧|音乐剧|戏剧|诗作|诗歌|诗词|散文|绘本|画作|雕塑|"
    r"演唱|执导|出版社出版|作品$")
_CERTAIN_PERSON = r"[，,（(]\s*[男女]\s*[，,）)。]|\d{4}年(?:\d{1,2}月)?(?:\d{1,2}日)?(?:出生|生)|出生于|生于\d"
_CERTAIN_PERSON_RE = re.compile(_CERTAIN_PERSON)
_PERSON_RE = re.compile(
    _CERTAIN_PERSON + "|"
    r"[（(][^（()）]{0,10}(?:\d{3,4}|[?？])\s*年?[^（()）]{0,12}[—－\-~～–至][^（()）]{0,16}[）)]|"   # 王都（？—929年）
    r"[，,]\s*(?:原名|本名|字|号|谥号)[^，,。；]{1,6}[，,。；]")
_YEAR_RE = re.compile(r"(?<!\d)(?:1\d{3}|20\d{2})(?!\d)")


# "沧海一粟，汉语成语，读音是…", "说明是一个汉语词汇，…", "英，汉语常用字（一级字），…"
_WORD_SUMMARY_RE = re.compile(r"(?:汉语|中文)(?:成语|词语|词汇|汉字|字词|熟语|俗语)|汉语(?:常用|通用|[一二三]级)(?:规范)?(?:汉)?字")


def is_work(rec: dict) -> bool:
    """A song, film, book, game …: the subtitle says so, or the summary opens
    with the title in 《》 (also after a few words: 同名电视剧《沧海一粟》…)."""
    title = rec.get("title") or ""
    if _WORK_LABEL_RE.search(rec.get("sense_label") or ""):
        return True
    opening = (rec.get("summary") or "").lstrip()[:len(title) + 10]
    return bool(title) and ("《" + title + "》" in opening or opening.startswith("「" + title + "」"))


def is_word(rec: dict) -> bool:
    """The article about the word or character itself: the subtitle says so
    (汉语词汇, 汉字 …), or the summary introduces the title as one
    (沧海一粟，汉语成语，…) and the article is not a work."""
    if _WORD_LABEL_RE.match((rec.get("sense_label") or "").strip()):
        return True
    title = rec.get("title") or ""
    opening = (rec.get("summary") or "").lstrip()[:len(title) + 24]
    return bool(_WORD_SUMMARY_RE.search(opening)) and not is_work(rec)


def is_person(rec: dict, certain: bool = False) -> bool:
    """A biography, going by the opening of the summary: ，男，/ 1968年1月出生,
    and unless `certain` also a year range in brackets or a courtesy name
    (（487~593）/ ，字明允，). The second group is right for people and wrong
    for dynasties and wars (后汉（947年—950年）), so it suits a guard that only
    has to err on the safe side, not a statement that the article is a
    person."""
    return bool((_CERTAIN_PERSON_RE if certain else _PERSON_RE).search((rec.get("summary") or "")[:80]))


def share_a_year(a: dict, b: dict) -> bool:
    """Both summaries name the same year (of birth, mostly): the one cheap
    sign that two biographies under one name are the same person."""
    return bool(set(_YEAR_RE.findall(a.get("summary") or "")) & set(_YEAR_RE.findall(b.get("summary") or "")))


_ORGANISATION_RE = re.compile(
    r"有限公司|有限责任公司|股份公司|集团公司|(?:公司|企业|集团|学校|学院|大学|中学|小学|幼儿园)"
    r"(?:成立|创办|创建|创立|始建|位于|坐落|地处|是一[家所间])|(?:成立|创办|创建|创立|始建)于")


def is_organisation(rec: dict) -> bool:
    """A company or a school, going by the opening of the summary."""
    return bool(_ORGANISATION_RE.search((rec.get("summary") or "")[:80]))


def sense_rank_key(rec: dict) -> tuple:
    """Sort key for senses sharing a title.  Lower key = better.

    1. the sense Baike itself shows for the bare title (reached by an id-less
       URL), when that is known;
    2. the word before other articles, and works (songs, films, books named
       after the word) last: someone looking up 时间 wants the word, not one
       of the songs called 时间;
    3. a real abstract before a fallback paragraph;
    4. the lower article id."""
    default = rec.get("is_default_sense")
    flags = rec.get("quality_flags") or []
    real_summary = not any(f in ("summary_from_section", "abstract_fallback") for f in flags)
    lemma = rec.get("lemma_id")
    kind = 0 if is_word(rec) else 2 if is_work(rec) else 1
    return (
        0 if default is True else 1,
        kind,
        0 if real_summary else 1,
        lemma if isinstance(lemma, int) else 10**12,
    )
