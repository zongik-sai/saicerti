#!/usr/bin/env python3
"""Data 2급(d2) 연습용 데이터 만들기 — 모두 지어낸(가상) 데이터다. 원본 시험 데이터는 쓰지 않는다.

사용: python3 tools/gen_d2_data.py
- public/data/d2/<이름>.csv    : 예시 데이터(학생이 보고 실행하는 파일, 변형 0)
- public/data/d2/<이름>.v1.csv : 숨은 채점 데이터 1(같은 열·같은 규칙, 값만 다름)
- public/data/d2/<이름>.v2.csv : 숨은 채점 데이터 2
- src/datasets/d2.json          : 화면의 [데이터 개요](변수 설명·앞 5행)·행 수
같은 시드로 늘 같은 파일이 나온다(random.Random만 사용).
"""
import csv
import io
import json
import math
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'public', 'data', 'd2')
CAT = os.path.join(ROOT, 'src', 'datasets', 'd2.json')
VARIANTS = 3
DATASETS = {}


def dataset(name, title, columns):
    def deco(fn):
        DATASETS[name] = {'title': title, 'columns': columns, 'fn': fn}
        return fn
    return deco


def clip(x, lo, hi):
    return max(lo, min(hi, x))


def pick(rng, table):
    """table: [(값, 가중치), ...]"""
    vals, ws = zip(*table)
    return rng.choices(vals, weights=ws)[0]


SYL = ['ar', 'be', 'ca', 'do', 'el', 'fi', 'ga', 'hu', 'in', 'lo', 'ma', 'ne', 'or', 'pa', 'ri', 'sa', 'te', 'ul', 'vi', 'zo', 'ty', 'ph', 'ko', 'mi']


def latin(rng, n=3, end=('us', 'a', 'is', 'um', 'ensis', 'ata')):
    w = ''.join(rng.choice(SYL) for _ in range(n))
    return (w + rng.choice(end)).lower()


# ── 1. 거미 목록(모의고사 13~16번 상황) ─────────────────────────────
@dataset('spyder', '거미 목록', [
    ('id', '식별 번호'), ('category_1', '1차 분류 기준(과)'), ('category_2', '2차 분류 기준(속)'), ('category_3', '3차 분류 기준(종)'),
    ('category_4', '4차 분류 기준(아종)'), ('author', '발견자'), ('year', '발견 연도'),
    ('dist_1', '주 서식지 1'), ('dist_2', '주 서식지 2'), ('dist_3', '주 서식지 3'), ('dist_4', '주 서식지 4'), ('dist_5', '주 서식지 5'),
])
def gen_spyder(rng, v):
    n = [5000, 4700, 5300][v]
    fams = [('Salticidae', 16), ('Linyphiidae', 13), ('Araneidae', 8), ('Theridiidae', 7), ('Lycosidae', 6), ('Gnaphosidae', 6),
            ('Zodariidae', 4), ('Thomisidae', 4), ('Oonopidae', 4), ('Pholcidae', 4), ('Agelenidae', 3), ('Dictynidae', 3),
            ('Tetragnathidae', 3), ('Hahniidae', 2), ('Clubionidae', 2), ('Sparassidae', 2), ('Ctenidae', 2), ('Corinnidae', 2),
            ('Mysmenidae', 1), ('Actinopodidae', 1)]
    fam_w = [(f, w * rng.uniform(0.7, 1.3)) for f, w in fams]
    genera = {f: [f[:4].capitalize() + latin(rng, 1, ('us', 'a', 'ops', 'ella', 'ia')) for _ in range(rng.randint(4, 9))] for f, _ in fams}
    surn = ['Hansen', 'Moreau', 'Tanaka', 'Kowalski', 'Silva', 'Novak', 'Okafor', 'Lindqvist', 'Ferreira', 'Ivanova', 'Chen', 'Park',
            'Muller', 'Rossi', 'Haddad', 'Nguyen', 'Sato', 'Lopez', 'Kruger', 'Petrov', 'Dubois', 'Costa', 'Yilmaz', 'Larsen', 'Gomez',
            'Wagner', 'Kim', 'Mendes', 'Santos', 'Berg', 'Ito', 'Horvat', 'Reyes', 'Ahmed', 'Olsen', 'Fischer', 'Barros', 'Nakamura',
            'Weber', 'Castro', 'Moller', 'Vargas', 'Ono', 'Pereira', 'Jensen']
    authors = []
    for i, s in enumerate(surn):
        if i < 6:  # 오래전 학자: 1900년대 초
            start = rng.randint(1900, 1925)
        elif i < 14:
            start = rng.randint(1926, 1975)
        else:
            start = rng.randint(1976, 2012)
        span = rng.randint(15, 40)
        w = rng.uniform(0.6, 1.4) * (1.6 if start >= 1976 else 1.0)
        authors.append([s, start, min(2024, start + span), w])
    top = rng.randrange(len(authors))
    authors[top][3] = sum(a[3] for a in authors) * 0.085  # 가장 왕성한 발견자(분명히 1등)
    for _ in range(6):  # 공동 발견자
        a, b = rng.sample(range(len(surn)), 2)
        authors.append([f'{surn[a]} & {surn[b]}', rng.randint(1980, 2010), 2024, 0.5])
    countries = ['Brazil', 'China', 'USA', 'India', 'Australia', 'Mexico', 'Japan', 'Peru', 'Colombia', 'South Africa', 'Indonesia',
                 'Madagascar', 'Kenya', 'Argentina', 'Chile', 'Korea', 'Vietnam', 'Spain', 'France', 'Italy', 'Russia', 'Turkey',
                 'Iran', 'Egypt', 'Canada', 'Venezuela', 'Ecuador']
    rows = []
    for i in range(n):
        f = pick(rng, fam_w)
        a = pick(rng, [(tuple(x[:3]), x[3]) for x in authors])
        year = rng.randint(a[1], a[2])
        k = pick(rng, [(1, 70), (2, 14), (3, 7), (4, 4), (5, 1.3 if year >= 2000 else 3.2)])
        ds = rng.sample(countries, k) + [None] * (5 - k)
        rows.append([i, f, rng.choice(genera[f]), latin(rng), latin(rng, 2) if rng.random() < 0.03 else None, a[0], year] + ds)
    return rows


# ── 2. 명품 편집숍 상품(모의고사 17~20번 상황) ──────────────────────
@dataset('shop_products', '편집숍 상품', [
    ('Brand', '브랜드'), ('category_1', '1차 카테고리'), ('category_2', '2차 카테고리'), ('category_3', '3차 카테고리'),
    ('product_code', '상품코드'), ('department', '상품구분(men·women·kids)'), ('eur_full_price', '상품 판매가(EUR)'), ('eur_disc_price', '상품 할인가(EUR)'),
])
def gen_shop(rng, v):
    n = [4000, 3800, 4200][v]
    brands = ['NORDLINE', 'VERANO', 'ATELIER RUE', 'KOVA', 'MAISON LUMEN', 'SOLENNE', 'BRAVA', 'OAKHART', 'MIRALDA', 'TESSERA',
              'GRAN VIA', 'HALDEN', 'ORSOLA', 'PIERRE NOIR', 'SAELO', 'VANTE', 'ELMIRA', 'CORVO', 'LUNETTA', 'ARDEN & CO',
              'BELLMORE', 'CASTELLO', 'FENWICK', 'IZARRA', 'JUNO PARIS', 'KESTREL', 'LORNA', 'MARIN', 'NOVA KID', 'PETIT ROSE']
    tiers = {}
    for b in brands:
        tiers[b] = pick(rng, [(0.0, 35), (0.30, 40), (0.55, 25)])
    tree = {
        'CLOTHING': {'KNITS': ['KNITTED SWEATERS', 'CARDIGANS'], 'T-SHIRTS & VESTS': ['T-SHIRTS', 'VESTS'], 'SHIRTS': ['CASUAL SHIRTS', 'FORMAL SHIRTS'],
                     'JACKETS': ['DENIM JACKETS', 'LEATHER JACKETS'], 'COATS': ['WOOL COATS', 'TRENCH COATS'], 'TROUSERS': ['JEANS', 'CHINOS']},
        'SHOES': {'SNEAKERS': ['LOW-TOP', 'HIGH-TOP'], 'BOOTS': ['ANKLE BOOTS', 'CHELSEA BOOTS'], 'LOAFERS': ['PENNY LOAFERS'], 'SANDALS': ['SLIDES']},
        'BAGS': {'TOTE BAGS': ['CANVAS TOTES'], 'SHOULDER BAGS': ['MINI BAGS', 'HOBO BAGS'], 'BACKPACKS': ['CITY BACKPACKS'], 'CLUTCHES': ['POUCHES']},
        'ACCESSORIES': {'HATS': ['CAPS', 'BEANIES'], 'BELTS': ['LEATHER BELTS'], 'SCARVES': ['SILK SCARVES', 'WOOL SCARVES'], 'SUNGLASSES': ['ROUND FRAMES'], 'WALLETS': ['CARD HOLDERS']},
        'JEWELRY': {'NECKLACES': ['PENDANTS'], 'RINGS': ['SIGNET RINGS'], 'EARRINGS': ['HOOPS', 'STUDS']},
        'TEEN BOY CLOTHING': {'TEEN TOPS': ['TEEN T-SHIRTS', 'TEEN HOODIES'], 'TEEN BOTTOMS': ['TEEN JEANS']},
        'TEEN GIRL CLOTHING': {'TEEN TOPS': ['TEEN T-SHIRTS', 'TEEN BLOUSES'], 'TEEN DRESSES': ['TEEN MINI DRESSES']},
        'BABY': {'BABY SETS': ['GIFT SETS'], 'BODYSUITS': ['LONG SLEEVE BODYSUITS']},
    }
    nan_rate = {'CLOTHING': 0.10, 'SHOES': 0.35, 'BAGS': 0.55, 'ACCESSORIES': 0.75, 'JEWELRY': 0.5, 'TEEN BOY CLOTHING': 0.3, 'TEEN GIRL CLOTHING': 0.3, 'BABY': 0.4}
    price = {'CLOTHING': (150, 900), 'SHOES': (200, 800), 'BAGS': (300, 2500), 'ACCESSORIES': (60, 400), 'JEWELRY': (100, 1500),
             'TEEN BOY CLOTHING': (40, 300), 'TEEN GIRL CLOTHING': (40, 300), 'BABY': (30, 200)}
    codes = rng.sample(range(19000000, 20000000), n)
    rows = []
    for i in range(n):
        dep = pick(rng, [('women', 50), ('men', 35), ('kids', 15)])
        if dep == 'kids':
            c1 = pick(rng, [('TEEN BOY CLOTHING', 40), ('TEEN GIRL CLOTHING', 40), ('BABY', 20)])
            b = pick(rng, [(x, 3 if x in ('NOVA KID', 'PETIT ROSE') else 1) for x in brands])
        else:
            c1 = pick(rng, [('CLOTHING', 45), ('SHOES', 15), ('BAGS', 15 if dep == 'women' else 12), ('ACCESSORIES', 15 if dep == 'women' else 22), ('JEWELRY', 6 if dep == 'women' else 2)])
            b = rng.choice(brands[:28])
        c2 = rng.choice(list(tree[c1]))
        c3 = None if rng.random() < nan_rate[c1] else rng.choice(tree[c1][c2])
        lo, hi = price[c1]
        full = round(math.exp(rng.uniform(math.log(lo), math.log(hi))), 2)
        t = tiers[b]
        rate = 0.0 if t == 0 else clip(t + rng.uniform(-0.05, 0.05), 0.05, 0.8)
        disc = round(full * (1 - rate), 2)
        rows.append([b, c1, c2, c3, codes[i], dep, f'{full:.2f}', f'{disc:.2f}'])
    return rows


# ── 3. 카페 주문 ─────────────────────────────────────────────
@dataset('cafe_orders', '카페 주문', [
    ('order_id', '주문 번호'), ('date', '주문 날짜(YYYY-MM-DD)'), ('hour', '주문 시각(시)'), ('store', '매장'), ('menu', '메뉴'),
    ('category', '메뉴 종류(coffee·tea·dessert·juice)'), ('price', '1개 가격(원)'), ('qty', '수량'), ('member', '회원 여부(Y·N)'), ('rating', '별점(1~5, 남기지 않으면 빈 값)'),
])
def gen_cafe(rng, v):
    n = [2500, 2400, 2600][v]
    menus = [('Americano', 'coffee', 4500, 22), ('Cafe Latte', 'coffee', 5000, 14), ('Vanilla Latte', 'coffee', 5500, 8), ('Cold Brew', 'coffee', 5000, 7),
             ('Espresso', 'coffee', 4000, 3), ('Green Tea', 'tea', 4500, 6), ('Earl Grey', 'tea', 4500, 4), ('Chamomile', 'tea', 4500, 3),
             ('Cheesecake', 'dessert', 6500, 6), ('Croissant', 'dessert', 4000, 7), ('Brownie', 'dessert', 5000, 5),
             ('Orange Juice', 'juice', 6000, 4), ('Mango Smoothie', 'juice', 6500, 5)]
    mw = [(m, m[3] * rng.uniform(0.85, 1.15)) for m in menus]
    stores = [('Gangnam', 30), ('Hongdae', 25), ('Jamsil', 25), ('Pangyo', 20)]
    rows = []
    for i in range(n):
        day = rng.randrange(92)
        y, mth, d = 2025, 3 + (day >= 31) + (day >= 61), day + 1 - (31 if day >= 31 else 0) - (30 if day >= 61 else 0)
        hour = pick(rng, [(h, {8: 9, 9: 8, 12: 9, 13: 8, 18: 7}.get(h, 3)) for h in range(8, 22)])
        m = pick(rng, mw)
        member = 'Y' if rng.random() < 0.4 else 'N'
        rating = None if rng.random() < 0.3 else clip(round(rng.gauss(4.1 if member == 'Y' else 3.7, 0.9)), 1, 5)
        rows.append([100001 + i, f'{y}-{mth:02d}-{d:02d}', hour, pick(rng, stores), m[0], m[1], m[2], pick(rng, [(1, 70), (2, 20), (3, 7), (4, 3)]), member, rating])
    return rows


# ── 4. 공공 자전거 대여 ─────────────────────────────────────────
@dataset('bike_rentals', '공공 자전거 대여', [
    ('rent_id', '대여 번호'), ('date', '대여 날짜(YYYY-MM-DD)'), ('hour', '대여 시각(시)'), ('station', '대여 정류소'), ('district', '구'),
    ('user_type', '이용자 구분(member·guest)'), ('age_group', '나이대(10s~60s, 모르면 빈 값)'), ('minutes', '이용 시간(분)'), ('distance_km', '이동 거리(km)'),
])
def gen_bike(rng, v):
    n = [3000, 2900, 3100][v]
    st = {'Mapo': ['Hapjeong', 'Mangwon', 'Gongdeok'], 'Gangnam': ['Yeoksam', 'Sinsa', 'Samseong'], 'Songpa': ['Jamsil', 'Munjeong', 'Garak'], 'Jongno': ['Gwanghwamun', 'Hyehwa', 'Jongno3ga']}
    dw = [('Mapo', 30), ('Gangnam', 28), ('Songpa', 24), ('Jongno', 18)]
    rows = []
    for i in range(n):
        day = rng.randrange(91)
        mth = 4 + (day >= 30) + (day >= 61)
        d = day + 1 - (30 if day >= 30 else 0) - (31 if day >= 61 else 0)
        hour = pick(rng, [(h, {7: 6, 8: 10, 9: 6, 17: 7, 18: 10, 19: 7}.get(h, 2 if 6 <= h <= 22 else 1)) for h in range(24)])
        dist = pick(rng, dw)
        ut = 'member' if rng.random() < 0.65 else 'guest'
        age = None if rng.random() < (0.04 if ut == 'member' else 0.15) else pick(rng, [('10s', 10), ('20s', 30), ('30s', 25), ('40s', 18), ('50s', 11), ('60s', 6)])
        mins = int(clip(round(math.exp(rng.gauss(math.log(16 if ut == 'member' else 30), 0.55))), 2, 180))
        km = round(mins * rng.uniform(0.12, 0.25), 2)
        rows.append([500001 + i, f'2025-{mth:02d}-{d:02d}', hour, rng.choice(st[dist]), dist, ut, age, mins, f'{km:.2f}'])
    return rows


# ── 5. 학생 성적 ─────────────────────────────────────────────
@dataset('student_scores', '학생 성적', [
    ('student_id', '학생 번호'), ('grade', '학년(1~3)'), ('class', '반(1~6)'), ('gender', '성별(M·F)'), ('club', '동아리(없으면 빈 값)'),
    ('math', '수학 점수'), ('korean', '국어 점수'), ('english', '영어 점수'), ('science', '과학 점수(결시하면 빈 값)'),
    ('study_hours', '주당 공부 시간(시간)'), ('absences', '결석 일수'),
])
def gen_students(rng, v):
    n = [900, 860, 940][v]
    bonus = {'coding': (6, 0, 2, 4), 'science': (4, 0, 1, 6), 'art': (-2, 3, 1, -1), 'music': (0, 2, 3, 0), 'sports': (-3, -2, -2, -2), 'reading': (0, 6, 4, 1), None: (0, 0, 0, 0)}
    rows = []
    for i in range(n):
        ab = rng.gauss(66, 14)
        club = pick(rng, [('coding', 14), ('science', 12), ('art', 12), ('music', 13), ('sports', 18), ('reading', 14), (None, 17)])
        b = bonus[club]
        sc = [int(clip(round(ab + b[k] + rng.gauss(0, 9)), 0, 100)) for k in range(4)]
        sci = None if rng.random() < 0.05 else sc[3]
        hours = round(clip((ab - 30) / 5 + rng.gauss(0, 2.5), 0, 20), 1)
        absn = int(clip(round(rng.expovariate(1 / 2.5)), 0, 15))
        rows.append([20250001 + i, rng.randint(1, 3), rng.randint(1, 6), rng.choice('MF'), club, sc[0], sc[1], sc[2], sci, f'{hours:.1f}', absn])
    return rows


# ── 6. 영화 ───────────────────────────────────────────────
@dataset('movies', '영화 정보', [
    ('movie_id', '영화 번호'), ('title', '제목'), ('genre', '장르'), ('country', '제작 국가(KR·US·JP·FR·UK·CN)'), ('release_year', '개봉 연도'),
    ('running_time', '상영 시간(분)'), ('audience', '관객 수(명)'), ('rating', '평점(0~10, 없으면 빈 값)'), ('director', '감독'),
])
def gen_movies(rng, v):
    n = [1500, 1450, 1550][v]
    w1 = ['Silent', 'Blue', 'Last', 'Hidden', 'Golden', 'Broken', 'Midnight', 'Wild', 'Lost', 'Little', 'Bright', 'Dark', 'Second', 'Paper']
    w2 = ['River', 'Harbor', 'Garden', 'Signal', 'Road', 'Letter', 'Island', 'Summer', 'City', 'Promise', 'Shadow', 'Dream', 'Bridge', 'Star']
    genres = [('action', 18, 125), ('comedy', 16, 108), ('drama', 22, 118), ('horror', 8, 98), ('animation', 10, 95), ('sf', 8, 130), ('romance', 9, 112), ('thriller', 9, 115)]
    countries = [('KR', 35), ('US', 30), ('JP', 12), ('FR', 8), ('UK', 8), ('CN', 7)]
    first = ['J. Han', 'M. Cho', 'S. Yoon', 'A. Reed', 'L. Grant', 'K. Mori', 'T. Abe', 'C. Laurent', 'P. Blake', 'W. Zhou', 'H. Seo', 'D. Moon',
             'R. Hale', 'E. Clarke', 'Y. Kang', 'N. Fujii', 'O. Martin', 'B. Hughes', 'I. Shin', 'G. Lim']
    dirs = [(d, rng.uniform(0.5, 1.5)) for d in first] + [(first[0], 4.0)]
    rows = []
    for i in range(n):
        g = pick(rng, [(x, x[1]) for x in genres])
        c = pick(rng, countries)
        yr = rng.randint(2000, 2024)
        rt = int(clip(round(rng.gauss(g[2], 12)), 75, 175))
        base = {'KR': 13.2, 'US': 13.5, 'JP': 12.0, 'FR': 11.0, 'UK': 11.4, 'CN': 12.2}[c]
        aud = int(round(math.exp(rng.gauss(base, 1.1)), -2))
        rating = None if rng.random() < 0.06 else round(clip(rng.gauss(6.8, 1.2), 1.0, 9.9), 1)
        rows.append([i + 1, f'{rng.choice(w1)} {rng.choice(w2)}', g[0], c, yr, rt, aud, rating, pick(rng, dirs)])
    return rows


# ── 7. 도시별 날씨 ─────────────────────────────────────────────
@dataset('weather_daily', '도시별 날씨', [
    ('date', '날짜(YYYY-MM-DD)'), ('city', '도시'), ('temp_max', '최고 기온(℃)'), ('temp_min', '최저 기온(℃)'),
    ('rain_mm', '강수량(mm, 측정 못 하면 빈 값)'), ('humidity', '습도(%)'), ('wind_speed', '풍속(m/s, 측정 못 하면 빈 값)'),
])
def gen_weather(rng, v):
    import datetime as dt
    year = [2024, 2023, 2022][v]
    cities = {'Seoul': (12.5, 0, 1.0), 'Busan': (15.0, 0.8, 1.3), 'Daegu': (14.5, 0.3, 0.9), 'Gwangju': (14.0, 0.5, 1.0), 'Jeju': (16.5, 1.2, 1.8)}
    rows = []
    d0 = dt.date(year, 1, 1)
    days = (dt.date(year + 1, 1, 1) - d0).days
    for k in range(days):
        day = d0 + dt.timedelta(days=k)
        season = -math.cos(2 * math.pi * (k - 15) / days)
        for c, (base, amp_shift, windy) in cities.items():
            tmax = round(base + 4 + 13 * season + rng.gauss(0, 2.2) - amp_shift * season * 2, 1)
            tmin = round(tmax - rng.uniform(5, 10), 1)
            wet = rng.random() < (0.45 if 5 <= day.month <= 8 else 0.25)
            rain = round(rng.gammavariate(1.2, 12 if 6 <= day.month <= 8 else 5), 1) if wet else 0.0
            rain = None if rng.random() < 0.03 else rain
            hum = int(clip(round(rng.gauss(70 if wet else 55, 10)), 20, 99))
            wind = None if rng.random() < 0.02 else round(clip(rng.gauss(2.5 * windy, 1.0), 0.3, 12), 1)
            rows.append([day.isoformat(), c, tmax, tmin, rain, hum, wind])
    return rows


# ── 8. 쇼핑몰 고객(군집 분석) ───────────────────────────────────
@dataset('customers', '쇼핑몰 고객', [
    ('customer_id', '고객 번호'), ('age', '나이'), ('gender', '성별(M·F)'), ('region', '지역'), ('membership', '회원 등급(basic·silver·gold)'),
    ('annual_spend', '1년 구매 금액(만 원)'), ('visits_per_month', '한 달 방문 횟수'), ('app_user', '앱 사용 여부(Y·N)'),
])
def gen_customers(rng, v):
    n = [1200, 1150, 1250][v]
    segs = [((30, 80), (1, 3), 50 + rng.uniform(-4, 4)), ((150, 250), (5, 8), 35 + rng.uniform(-4, 4)), ((400, 600), (10, 15), 15)]
    rows = []
    for i in range(n):
        s = pick(rng, [(k, segs[k][2]) for k in range(3)])
        (s_lo, s_hi), (v_lo, v_hi), _ = segs[s]
        spend = rng.randint(s_lo, s_hi)
        visits = rng.randint(v_lo, v_hi)
        mem = pick(rng, [[('basic', 80), ('silver', 18), ('gold', 2)], [('basic', 25), ('silver', 60), ('gold', 15)], [('basic', 5), ('silver', 30), ('gold', 65)]][s])
        rows.append([30001 + i, rng.randint(19, 69), rng.choice('MF'), pick(rng, [('Seoul', 35), ('Gyeonggi', 30), ('Busan', 12), ('Incheon', 10), ('Daegu', 8), ('Daejeon', 5)]),
                     mem, spend, visits, 'Y' if rng.random() < [0.4, 0.6, 0.8][s] else 'N'])
    return rows


# ── 9. 중고차 ───────────────────────────────────────────────
@dataset('used_cars', '중고차 매물', [
    ('car_id', '매물 번호'), ('brand', '제조사'), ('model', '모델'), ('year', '연식(연도)'), ('mileage_km', '주행 거리(km)'),
    ('fuel', '연료(gasoline·diesel·hybrid·electric, 모르면 빈 값)'), ('transmission', '변속기(auto·manual)'), ('price', '가격(만 원)'), ('accident', '사고 이력(Y·N)'),
])
def gen_cars(rng, v):
    n = [1600, 1550, 1650][v]
    brands = [('Hyundai', 30, 1.0), ('Kia', 26, 1.0), ('Genesis', 8, 1.8), ('Renault', 6, 0.9), ('Chevrolet', 6, 0.9), ('BMW', 9, 2.0), ('Benz', 8, 2.2), ('Toyota', 7, 1.2)]
    rows = []
    for i in range(n):
        b = pick(rng, [(x, x[1]) for x in brands])
        yr = rng.randint(2012, 2024)
        age = 2025 - yr
        km = int(round(age * rng.uniform(7000, 20000) + rng.uniform(0, 5000), -2))
        fuel = None if rng.random() < 0.04 else pick(rng, [('gasoline', 50), ('diesel', 25 if yr < 2019 else 12), ('hybrid', 15), ('electric', 3 if yr < 2019 else 12)])
        acc = 'Y' if rng.random() < 0.2 else 'N'
        price = 3000 * b[2] * (0.88 ** age) * (1 - km / 400000) * (0.85 if acc == 'Y' else 1.0) * rng.uniform(0.85, 1.15)
        rows.append([700001 + i, b[0], f'{b[0][:2].upper()}-{rng.choice("ABCDE")}{rng.randint(1, 9)}', yr, km, fuel, 'manual' if rng.random() < 0.08 else 'auto', int(round(price, -1)), acc])
    return rows


def write_csv(path, head, rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator='\n')
    w.writerow(head)
    for r in rows:
        w.writerow(['' if x is None else x for x in r])
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(buf.getvalue())


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(os.path.dirname(CAT), exist_ok=True)
    cat = {}
    for name, d in DATASETS.items():
        head = [c for c, _ in d['columns']]
        counts = []
        sample = None
        for v in range(VARIANTS):
            rng = random.Random(f'saicerti-d2-{name}-{v}')
            rows = d['fn'](rng, v)
            assert all(len(r) == len(head) for r in rows), name
            fn = f'{name}.csv' if v == 0 else f'{name}.v{v}.csv'
            write_csv(os.path.join(OUT, fn), head, rows)
            counts.append(len(rows))
            if v == 0:
                sample = [['NaN' if x is None else str(x) for x in r] for r in rows[:5]]
        cat[f'{name}.csv'] = {'title': d['title'], 'rows': counts, 'columns': [{'name': c, 'desc': t} for c, t in d['columns']], 'sample': sample}
    with open(CAT, 'w', encoding='utf-8') as f:
        json.dump(cat, f, ensure_ascii=False, indent=1)
        f.write('\n')
    total = sum(os.path.getsize(os.path.join(OUT, x)) for x in os.listdir(OUT))
    print(f'✓ 데이터 {len(DATASETS)}종 × {VARIANTS}변형 → public/data/d2/ ({total / 1e6:.1f}MB), 개요 → src/datasets/d2.json')


if __name__ == '__main__':
    main()
