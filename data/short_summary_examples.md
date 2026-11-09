# Why summaries under 15 characters are dropped — sampled examples

Sample: 360,000 raw rows from six offsets of the 16.8 GB file (60,000 consecutive rows at 0 %, 10 %, 30 %, 50 %, 70 %, 90 %).

| outcome | rows | share |
|---|---:|---:|
| kept | 256,627 | 71.3 % |
| summary_too_short | 32,183 | 8.9 % |
| summary_too_short_fallback | 57,731 | 16.0 % |
| no_summary_no_sections | 12,469 | 3.5 % |
| title_drop | 990 | 0.3 % |
| rescued_by_first_section | 2,782 | 0.8 % |

## summary_too_short (32,183 in sample)

The `summary` field is present, but after cleaning it is shorter than 15 characters, and the first paragraph of the first section is also too short (or there are no sections).

### What the short text looks like

| category | rows | share |
|---|---:|---:|
| key:value line | 8,347 | 25.9 % |
| short_prose_fragment | 7,709 | 24.0 % |
| equals_title | 7,447 | 23.1 % |
| title_plus_few_chars | 5,154 | 16.0 % |
| no_chinese (pinyin/latin/digits) | 3,018 | 9.4 % |
| empty_after_cleaning | 508 | 1.6 % |

### Number of sections on the dropped rows

| sections | rows |
|---|---:|
| 0 | 31,107 |
| 1 | 244 |
| 2 | 299 |
| 3+ | 533 |

### Would anything else on the page qualify?

| situation | rows | share |
|---|---:|---:|
| no sections at all | 31,107 | 96.7 % |
| a later paragraph/section is >= 15 | 608 | 1.9 % |
| only by joining several short lines | 420 | 1.3 % |
| no paragraph anywhere >= 15 chars | 40 | 0.1 % |
| second paragraph of first section is >= 15 | 8 | 0.0 % |

### Most common first-section titles on dropped rows

基本信息 (98), 基本参数 (54), 重要参数 (53), 歌词 (44), 光学参数 (41), 近义词 (36), 个人简介 (32), 基本资料 (23), 所属科类 (22), 图书信息 (20), 简介 (20), 目录 (18), 主要性能 (17), 人物简介 (11), 名称类别 (9)

### Examples

**key:value line**

- **同邑** — http://baike.baidu.com/view/3140654.htm
  - raw summary: `'【名称】：同邑'`
  - cleaned text used for the length test (7 chars): `'【名称】：同邑'`
  - no sections
- **江门市博士后管理工作暂行办法** — http://baike.baidu.com/view/3075303.htm
  - raw summary: `'发文单位：江门市人民政府 '`
  - cleaned text used for the length test (12 chars): `'发文单位：江门市人民政府'`
  - no sections
- **刘石麟** — http://baike.baidu.com/view/3965761.htm
  - raw summary: `'姓\u3000\u3000名：刘石麟\u3000\u3000'`
  - cleaned text used for the length test (6 chars): `'姓名：刘石麟'`
  - no sections
- **tyloo.Miss** — http://baike.baidu.com/view/3705545.htm
  - raw summary: `'tyloo.Miss的简介：'`
  - cleaned text used for the length test (14 chars): `'tyloo.Miss的简介：'`
  - no sections

**short_prose_fragment**

- **AN-TONE 32824H** — http://baike.baidu.com/view/9493732.htm
  - raw summary: `'重要参数 '`
  - cleaned text used for the length test (4 chars): `'重要参数'`
  - no sections
- **蒋璟璟** — http://baike.baidu.com/view/8488350.htm
  - raw summary: `'中共松阳县委常委、统战部部长'`
  - cleaned text used for the length test (14 chars): `'中共松阳县委常委、统战部部长'`
  - no sections
- **三洋CK29FS30P** — http://baike.baidu.com/view/1012506.htm
  - raw summary: `'关键属性组 '`
  - cleaned text used for the length test (5 chars): `'关键属性组'`
  - no sections
- **肥城阿斯德化工有限公司** — http://baike.baidu.com/view/430897.htm
  - raw summary: `'公司简介'`
  - cleaned text used for the length test (4 chars): `'公司简介'`
  - no sections

**equals_title**

- **英国电影学院** — http://baike.baidu.com/view/216336.htm
  - raw summary: `'英国电影学院\n'`
  - cleaned text used for the length test (6 chars): `'英国电影学院'`
  - no sections
- **合成镜头** — http://baike.baidu.com/view/60293.htm
  - raw summary: `'合成镜头\n'`
  - cleaned text used for the length test (4 chars): `'合成镜头'`
  - no sections
- **高祥栋** — http://baike.baidu.com/view/228519.htm
  - raw summary: `'高祥栋'`
  - cleaned text used for the length test (3 chars): `'高祥栋'`
  - no sections
- **宁波瑞应亭** — http://baike.baidu.com/view/3241739.htm
  - raw summary: `'宁波瑞应亭'`
  - cleaned text used for the length test (5 chars): `'宁波瑞应亭'`
  - no sections

**title_plus_few_chars**

- **急脉缓灸** — http://baike.baidu.com/view/373499.htm
  - raw summary: `'【成语】急脉缓灸'`
  - cleaned text used for the length test (8 chars): `'【成语】急脉缓灸'`
  - no sections
- **皮革雾化测试仪** — http://baike.baidu.com/view/3196435.htm
  - raw summary: `'\xa0\xa0皮革雾化测试仪皮革雾化测试仪'`
  - cleaned text used for the length test (14 chars): `'皮革雾化测试仪皮革雾化测试仪'`
  - no sections
- **笔记本处理器** — http://baike.baidu.com/view/1356509.htm
  - raw summary: `'一、笔记本处理器的优势'`
  - cleaned text used for the length test (11 chars): `'一、笔记本处理器的优势'`
  - no sections
- **微故** — http://baike.baidu.com/view/6941666.htm
  - raw summary: `'【词目】微故'`
  - cleaned text used for the length test (6 chars): `'【词目】微故'`
  - no sections

**no_chinese (pinyin/latin/digits)**

- **扶树** — http://baike.baidu.com/view/6971509.htm
  - raw summary: `'fú shù ㄈㄨˊ ㄕㄨˋ'`
  - cleaned text used for the length test (14 chars): `'fú shù ㄈㄨˊ ㄕㄨˋ'`
  - no sections
- **私系** — http://baike.baidu.com/view/6787970.htm
  - raw summary: `'sī xì ㄙㄧ ㄒㄧˋ '`
  - cleaned text used for the length test (12 chars): `'sī xì ㄙㄧ ㄒㄧˋ'`
  - no sections
- **父母国** — http://baike.baidu.com/view/124365.htm
  - raw summary: `'fu mu guo'`
  - cleaned text used for the length test (9 chars): `'fu mu guo'`
  - no sections
- **瞀忧** — http://baike.baidu.com/view/7845251.htm
  - raw summary: `'mào yōu ㄇㄠˋ ㄧㄡ'`
  - cleaned text used for the length test (14 chars): `'mào yōu ㄇㄠˋ ㄧㄡ'`
  - no sections

**empty_after_cleaning**

- **哈苏 503CW** — http://baike.baidu.com/view/8911766.htm
  - raw summary: `'[1]'`
  - cleaned text used for the length test (0 chars): `''`
  - first section: title `主要性能`, first paragraph `'机身特性胶片相机'` (1 sections)
  - first paragraph anywhere ≥ 15 chars: `'传感器尺寸 36.7×36.7mm'`
- **翔升迷尔H61T海外版** — http://baike.baidu.com/view/8764263.htm
  - raw summary: `'[1]'`
  - cleaned text used for the length test (0 chars): `''`
  - first section: title `重要参数`, first paragraph `'主芯片组：Intel H61'` (2 sections)
  - first paragraph anywhere ≥ 15 chars: `'CPU类型：Core i7/Core i5/Core i3'`
- **品人录** — http://baike.baidu.com/view/353237.htm
  - raw summary: `'\xa0\xa0[1]'`
  - cleaned text used for the length test (0 chars): `''`
  - first section: title `基本信息`, first paragraph `'·作者:易中天'` (4 sections)
  - first paragraph anywhere ≥ 15 chars: `'·ISBN：7532120198'`
- **联想 E209** — http://baike.baidu.com/view/8943688.htm
  - raw summary: `'[1]'`
  - cleaned text used for the length test (0 chars): `''`
  - first section: title `重要功能`, first paragraph `'网络制式：支持 GPRS'` (1 sections)
  - first paragraph anywhere ≥ 15 chars: `'主屏参数：26万色TFT；240×320像素，2.4英寸；'`

## summary_too_short_fallback (57,731 in sample)

The `summary` field is null/empty. The first paragraph of the first section was used instead and it is shorter than 15 characters.

### What the short text looks like

| category | rows | share |
|---|---:|---:|
| key:value line | 42,751 | 74.1 % |
| short_prose_fragment | 6,154 | 10.7 % |
| title_plus_few_chars | 3,928 | 6.8 % |
| equals_title | 2,927 | 5.1 % |
| no_chinese (pinyin/latin/digits) | 1,241 | 2.1 % |
| empty_after_cleaning | 730 | 1.3 % |

### Number of sections on the dropped rows

| sections | rows |
|---|---:|
| 0 | 0 |
| 1 | 1,932 |
| 2 | 19,726 |
| 3+ | 36,073 |

### Would anything else on the page qualify?

| situation | rows | share |
|---|---:|---:|
| only by joining several short lines | 24,643 | 42.7 % |
| second paragraph of first section is >= 15 | 19,915 | 34.5 % |
| a later paragraph/section is >= 15 | 11,348 | 19.7 % |
| no paragraph anywhere >= 15 chars | 1,825 | 3.2 % |

### Most common first-section titles on dropped rows

基本信息 (15,505), 图书信息 (6,191), 重要参数 (5,353), 个人简介 (2,278), 简介 (2,070), 个人资料 (1,205), 游戏信息 (1,002), 基本介绍 (867), 基本资料 (849), 基本参数 (656), 歌曲信息 (400), 概述 (332), 作者简介 (314), 词语信息 (312), 食材明细 (304)

### Examples

**key:value line**

- **广东省人民政府参事室** — http://baike.baidu.com/view/10246165.htm
  - cleaned text used for the length test (14 chars): `'地址：广州市解放北路542号'`
  - first section: title `基本信息`, first paragraph `'地址：广州市解放北路542号'` (3 sections)
  - first paragraph anywhere ≥ 15 chars: `'（1）围绕党和政府的中心工作，调查研究，提出意见和建议；'`
- **新疆远志** — http://baike.baidu.com/view/4256177.htm
  - cleaned text used for the length test (7 chars): `'药名：新疆远志'`
  - first section: title `基本信息`, first paragraph `'药名：新疆远志'` (7 sections)
  - first paragraph anywhere ≥ 15 chars: `'汉语拼音：xin jiang yuan zhi'`
- **改变孩子一生的教育方法：一本造就天才的传世经典** — http://baike.baidu.com/view/8328173.htm
  - cleaned text used for the length test (8 chars): `'作者：徐汉林编著'`
  - first section: title `基本信息`, first paragraph `'作者：徐汉林编著'` (5 sections)
  - first paragraph anywhere ≥ 15 chars: `'I S B N：9787801383617'`
- **Final Frontier** — http://baike.baidu.com/view/6210017.htm
  - cleaned text used for the length test (11 chars): `'所属艺人：MC Ren'`
  - first section: title `单曲信息`, first paragraph `'所属艺人：MC Ren'` (4 sections)
  - first paragraph anywhere ≥ 15 chars: `'来自专辑：Kizz My Black Azz'`

**short_prose_fragment**

- **昆阳城** — http://baike.baidu.com/view/8384272.htm
  - cleaned text used for the length test (10 chars): `'苏洵，字明允号老泉。'`
  - first section: title `作者介绍`, first paragraph `'苏洵，字明允号老泉。'` (2 sections)
  - first paragraph anywhere ≥ 15 chars: `'北宋散文家。汉族，与其子苏轼、苏辙合称“三苏”,均被列入“唐宋八大家”。'`
- **分开还是深爱** — http://baike.baidu.com/view/6302067.htm
  - cleaned text used for the length test (8 chars): `'道别共聚又重离别'`
  - first section: title `歌曲歌词`, first paragraph `'道别共聚又重离别'` (2 sections)
  - first paragraph anywhere ≥ 15 chars: `'张智霖，香港知名艺人。其代表作有《白发魔女》、《谈判专家》、《澳门街》、《水浒无间道》、《陆小凤系列》等。从1991年入行至今，已经踏入娱乐圈二十年了。'`
- **三星U100** — http://baike.baidu.com/view/1070703.htm
  - cleaned text used for the length test (11 chars): `'型号 SGH-U100'`
  - first section: title `外观设计`, first paragraph `'型号 SGH-U100'` (4 sections)
  - first paragraph anywhere ≥ 15 chars: `'网络制式 GSM 900/1800/1900,EDGE'`
- **GBC Auto+100** — http://baike.baidu.com/view/9935383.htm
  - cleaned text used for the length test (4 chars): `'综述介绍'`
  - first section: title `重要参数`, first paragraph `'综述介绍'` (1 sections)
  - first paragraph anywhere ≥ 15 chars: `'其他特性：可碎订书钉、曲别针、信用卡'`

**title_plus_few_chars**

- **杂反** — http://baike.baidu.com/view/1508911.htm
  - cleaned text used for the length test (14 chars): `'读音zá fǎn解释（杂反）'`
  - first section: title `释义`, first paragraph `'读音zá fǎn解释（杂反）'` (2 sections)
  - first paragraph anywhere ≥ 15 chars: `'1.不合正道。《韩非子·显学》：“愚诬之学，杂反之行，明主弗受也。”陈奇猷集释：“儒墨各派之行，是为杂行。与法相背之行，谓之反行。”'`
- **莫愁曲** — http://baike.baidu.com/view/3434904.htm
  - cleaned text used for the length test (9 chars): `'【名称】《莫愁曲》'`
  - first section: title `作品信息`, first paragraph `'【名称】《莫愁曲》'` (4 sections)
  - first paragraph anywhere ≥ 15 chars: `'这是一首借乐府旧题另翻新意的诗作。《莫愁乐》是唐时流行音乐，《旧唐书·音乐志》云：“《莫愁乐》出于《石城乐》。石城有女子名莫愁，善歌谣。故歌云：莫愁在何处，莫愁石城西。艇子打两桨，催送莫愁来。”张祜此'`
- **焦溜肥肠** — http://baike.baidu.com/view/154450.htm
  - cleaned text used for the length test (8 chars): `'【菜名】焦溜肥肠'`
  - first section: title `菜品信息`, first paragraph `'【菜名】焦溜肥肠'` (3 sections)
  - first paragraph anywhere ≥ 15 chars: `'【特点】颜色金黄，肥肠，外焦内嫩，咸甜味香，老幼欢迎，常吃不厌，吃一口就想吃第二口，源源不绝！'`
- **刘忠朴** — http://baike.baidu.com/view/4564527.htm
  - cleaned text used for the length test (5 chars): `'姓名刘忠朴'`
  - first section: title `个人简介`, first paragraph `'姓名刘忠朴'` (2 sections)
  - first paragraph anywhere ≥ 15 chars: `'职务深圳市人居环境委员会党组书记、主任'`

**equals_title**

- **NU 209 E轴承** — http://baike.baidu.com/view/9938276.htm
  - cleaned text used for the length test (10 chars): `'NU 209 E轴承'`
  - first section: title `NU 209 E轴承详细参数`, first paragraph `'NU 209 E轴承'` (2 sections)
  - first paragraph anywhere ≥ 15 chars: `'详细说明内圈无挡边圆柱滚子轴承（NU 0000 型）'`
- **醋泡白菜胡萝卜** — http://baike.baidu.com/view/343111.htm
  - cleaned text used for the length test (7 chars): `'醋泡白菜胡萝卜'`
  - first section: title `制作方法一`, first paragraph `'醋泡白菜胡萝卜'` (3 sections)
  - first paragraph anywhere ≥ 15 chars: `'调料：盐、白糖、醋精、花椒、干辣椒、姜'`
- **人工鱼礁关键技术研究与示范** — http://baike.baidu.com/view/6778026.htm
  - cleaned text used for the length test (13 chars): `'人工鱼礁关键技术研究与示范'`
  - first section: title `图书信息`, first paragraph `'人工鱼礁关键技术研究与示范'` (2 sections)
  - first paragraph anywhere ≥ 15 chars: `'定价：￥90.00 作者：贾晓平等著'`
- **通胀预期下的理财之道** — http://baike.baidu.com/view/3382203.htm
  - cleaned text used for the length test (10 chars): `'通胀预期下的理财之道'`
  - first section: title `图书信息`, first paragraph `'通胀预期下的理财之道'` (4 sections)
  - first paragraph anywhere ≥ 15 chars: `'I S B N：9787111296096'`

**no_chinese (pinyin/latin/digits)**

- **尼尔岱尔蒙德** — http://baike.baidu.com/view/1920157.htm
  - cleaned text used for the length test (12 chars): `'Neil Diamond'`
  - first section: title `歌手简介`, first paragraph `'Neil Diamond'` (3 sections)
  - first paragraph anywhere ≥ 15 chars: `'尼尔·岱尔蒙德(Neil Diamond)1941年2月24日出生于美国纽约。早在十几岁时，Diamond 就和同一个高中的Neil Sedak和Bobby Feldman一起组成了Strangelo'`
- **虢仲簠** — http://baike.baidu.com/view/9875498.htm
  - cleaned text used for the length test (12 chars): `'guó zhòng fǔ'`
  - first section: title `注音`, first paragraph `'guó zhòng fǔ'` (2 sections)
  - first paragraph anywhere ≥ 15 chars: `'虢仲簠，西周晚期。1992年12月河南三门峡市上村岭虢国墓地（M2013.2）。通高8.9、口横33、口纵25、腹深5.8釐米。失盖，平沿方唇，腹壁斜收成平底，腹两侧有一对兽首耳，矩形圈足正中有括弧形'`
- **玩意** — http://baike.baidu.com/view/583296.htm
  - cleaned text used for the length test (6 chars): `'wán yì'`
  - first section: title `玩意：`, first paragraph `'wán yì'` (2 sections)
  - first paragraph anywhere ≥ 15 chars: `'1、玩具、小摆设或有趣的事物；也泛指东西：小玩意|他手里拿的是什么玩意。'`
- **兔褐** — http://baike.baidu.com/view/8125563.htm
  - cleaned text used for the length test (13 chars): `'tù hè ㄊㄨˋ ㄏㄜˋ'`
  - first section: title `词语注音`, first paragraph `'tù hè ㄊㄨˋ ㄏㄜˋ'` (2 sections)
  - first paragraph anywhere ≥ 15 chars: `'(1).兔毛布。唐李肇《唐国史补》卷下：“宣州以兔毛为褐，亚于锦绮，复有染丝织者尤妙，故时人以为兔褐真不如假也。”宋陆游《新裁短褐接客以代戎服或以为慢戏作》诗：“虽云裁兔褐，不拟坐渔扉。”'`

**empty_after_cleaning**

- **汕头市金中南校** — http://baike.baidu.com/view/6200326.htm
  - cleaned text used for the length test (0 chars): `''`
  - first section: title `学校概况`, first paragraph `''` (7 sections)
  - first paragraph anywhere ≥ 15 chars: `'汕头金山中学南区学校（简称金中南校）创建于2003年，是全日制住宿完全中学，为汕头市直属中学、汕头市一级学校。学校依托广东名校汕头金中丰富优质的办学资源，采用金中的教育教学管理模式，全面贯彻党的教育方'`
- **嫂子很美** — http://baike.baidu.com/view/7222074.htm
  - cleaned text used for the length test (0 chars): `''`
  - first section: title `作品封面`, first paragraph `''` (4 sections)
  - first paragraph anywhere ≥ 15 chars: `'点击：12553762 推荐：1322 总字数：1956271 总章节：826'`
- **上海琛泰投资有限公司** — http://baike.baidu.com/view/10178075.htm
  - cleaned text used for the length test (0 chars): `''`
  - first section: title `公司LOGO`, first paragraph `''` (7 sections)
  - first paragraph anywhere ≥ 15 chars: `'上海琛泰投资有限公司,位于世界级地标—上海市北外滩，黄浦江畔。从事古玩艺术品的投资，是大型的艺术收藏品鉴定及交易平台。与国内各大知名博物馆、博物院、鉴定检测机构合作，为客户藏品进行全方位权威鉴定。公司'`
- **乙状结肠直肠切除端端吻合术** — http://baike.baidu.com/view/2958018.htm
  - cleaned text used for the length test (0 chars): `''`
  - first section: title `简介`, first paragraph `''` (6 sections)
  - first paragraph anywhere ≥ 15 chars: `'1.肿瘤下缘在肛门口以上超出12cm的直肠、乙状结肠癌。'`

