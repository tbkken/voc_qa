"""生成模拟 VoC 数据 CSV,字段和用户真实数据完全一致。"""
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)

CHANNELS = ["用户反馈", "电商", "社媒", "客服热线", "官网", "应用市场", "线下门店"]
BUSINESS_CATS = ["电商", "售后服务", "产品质量", "客户服务", "软件体验", "物流配送", "价格政策", "营销活动"]
EMOTIONS = ["负向声量", "正向声量", "中性声量"]
EMOTION_WEIGHTS = [0.3, 0.45, 0.25]

FIRST_CATS = ["电商", "售后服务", "产品质量", "客户服务", "软件体验", "物流配送", "价格政策", "营销活动"]

# 五级分类 -> 所属一级分类
FIFTH_CATS = {
    "客服推脱责任": "客户服务", "门店虚假承诺": "电商", "系统应用不兼容": "软件体验",
    "退换货困难": "售后服务", "手机频繁死机": "产品质量", "价格承诺不兑现": "电商",
    "维修周期长": "售后服务", "发货延迟": "物流配送", "摄像头异常": "产品质量",
    "信号差": "产品质量", "客服态度恶劣": "客户服务", "券无法使用": "营销活动",
    "续航优秀": "产品质量", "拍照满意": "产品质量", "系统流畅": "软件体验",
    "外观精致": "产品质量", "价格偏高": "价格政策", "发货及时": "物流配送",
    "以旧换新便利": "营销活动", "快充给力": "产品质量",
}

POS_KEYWORDS = ["续航强-正向", "手感好-正向", "屏幕清晰-正向", "外观精致-正向", "系统流畅-正向", "快充-正向", "散热好-正向"]
NEG_KEYWORDS = ["客服推脱-负向观点", "死机-负向观点", "摄像头对焦-负向观点", "退货困难-负向观点",
                "应用不兼容-负向观点", "虚假承诺-负向观点", "维修慢-负向观点", "信号差-负向观点",
                "闪退-负向观点", "发货慢-负向观点", "拍照弱-负向观点", "券核销-负向观点"]
NEU_KEYWORDS = ["价格-中性", "性价比-中性", "以旧换新-中性"]

NEG_CONTENT_TEMPLATES = [
    "不要给{place}卖华为手机了,购买手机时不提前告知手机很多应用不兼容,买回来第二天死机...",
    "新买的机器拍照对焦一直漂移,拍移动物体几乎没有一张能用的,官方客服说是正常现象...",
    "买了不到7天想退货,客服先是说要检测,检测完说有使用痕迹不能退,真的是各种推诿各种理由...",
    "工作常用的几个App在新系统上频繁闪退,向客服反映后只给了一句等后续更新...",
    "{place}门店销售时承诺的赠品,到货后说没有了,打电话各种推脱,这是一个商家该说的话?",
    "维修寄过去快一个月了,联系客服每次都说在排队,这服务真的太让人失望...",
    "新机刚用两周摄像头就出现异常,去售后说要等鉴定,结果一直拖着...",
    "以旧换新的券在付款时提示无法使用,联系客服说是系统问题,让我等通知...",
]
POS_CONTENT_TEMPLATES = [
    "这次买的新机,续航真的比上一代强太多了,晚上睡前90%,早起还有82%,值得推荐...",
    "手感一流,外观精致,拿到手就爱不释手,这代工艺提升明显...",
    "系统比之前流畅很多,而且很多细节都做得很到位,整体体验超预期...",
    "快充给力,30分钟能充到80%多,日常出门再也不用焦虑电量了...",
    "拍照效果惊艳,夜景和人像模式都很能打,朋友圈发了都说专业...",
    "屏幕素质非常好,色彩准确,日常使用护眼效果也不错...",
]
NEU_CONTENT_TEMPLATES = [
    "价格确实不便宜,不过配置给的挺足,看个人需求吧...",
    "以旧换新的流程还算顺畅,旧机估价大致符合预期...",
    "整体表现中规中矩,没什么特别惊艳的地方也没什么大毛病...",
]

PLACES = ["句容市华阳街道宝塔路18号风云手机电脑店", "镇江润州区新城广场授权店",
          "常州钟楼区万达3楼华为门店", "南京建邺区龙江手机城",
          "无锡新吴区旺庄路旗舰店", "徐州鼓楼区淮海东路门店"]


def gen_row(row_date: datetime, idx: int) -> list:
    emotion = random.choices(EMOTIONS, weights=EMOTION_WEIGHTS)[0]

    if emotion == "负向声量":
        fifth = random.choice([f for f in FIFTH_CATS if FIFTH_CATS[f] not in ("营销活动",)][:12])
        content = random.choice(NEG_CONTENT_TEMPLATES).format(place=random.choice(PLACES))
        keywords = random.choice(NEG_KEYWORDS)
    elif emotion == "正向声量":
        fifth = random.choice(["续航优秀", "拍照满意", "系统流畅", "外观精致", "快充给力"])
        content = random.choice(POS_CONTENT_TEMPLATES)
        keywords = random.choice(POS_KEYWORDS)
    else:
        fifth = random.choice(["价格偏高", "以旧换新便利", "发货及时"])
        content = random.choice(NEU_CONTENT_TEMPLATES)
        keywords = random.choice(NEU_KEYWORDS)

    first_cat = FIFTH_CATS.get(fifth, "其他")
    business_cat = first_cat
    channel = random.choice(CHANNELS)

    # comment_time: 当日随机时刻
    ct = row_date.replace(hour=random.randint(8, 23), minute=random.randint(0, 59), second=random.randint(0, 59))

    return [
        row_date.strftime("%Y%m%d"),                      # pt_d
        f"17{random.randint(10**13, 10**14 - 1)}",        # source_sound_id
        ct.strftime("%Y-%m-%d %H:%M:%S"),                  # comment_time
        business_cat,                                       # business_category_name
        content,                                            # content
        1,                                                  # is_show
        channel,                                            # data_channel
        emotion,                                            # emotion
        first_cat,                                          # first_category
        fifth,                                              # fifth_category
        keywords,                                           # keywords_emotion
    ]


def generate(output: Path, days: int = 180, rows_per_day_avg: int = 700) -> int:
    """生成 days 天的数据,默认约 12 万行。"""
    end_date = datetime(2026, 4, 22)
    start_date = end_date - timedelta(days=days - 1)
    header = ["pt_d", "source_sound_id", "comment_time", "business_category_name",
              "content", "is_show", "data_channel", "emotion",
              "first_category", "fifth_category", "keywords_emotion"]
    total = 0
    with open(output, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        cur = start_date
        while cur <= end_date:
            # 随机波动 + 近期上升趋势
            day_offset = (cur - start_date).days
            rows = int(rows_per_day_avg * (0.8 + 0.5 * day_offset / days) + random.randint(-80, 80))
            for i in range(rows):
                w.writerow(gen_row(cur, i))
                total += 1
            cur += timedelta(days=1)
    return total


if __name__ == "__main__":
    out = Path(__file__).resolve().parent / "sample_voc.csv"
    n = generate(out)
    size_mb = out.stat().st_size / 1024 / 1024
    print(f"✅ 生成 {n} 行 → {out} ({size_mb:.1f} MB)")
