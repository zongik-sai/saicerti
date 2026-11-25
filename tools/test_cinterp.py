#!/usr/bin/env python3
"""C 인터프리터(src/grader/cinterp.py) 회귀 테스트.

사용: python3 tools/test_cinterp.py [-k 이름일부] [-v]
1. C 프로그램 묶음(main에서 printf)을 gcc(-O0 -fsanitize=address,undefined)와 인터프리터로 각각 실행해 출력·종료 코드가 같은지
2. run_cases_c(harness.py)로 solution 함수 채점 — 기댓값과 같고, tools/cref.py(gcc 대조)의 결과와도 같은지
3. 런타임 오류(범위 밖·초기화 안 한 값·NULL·시간 초과·깊은 재귀 등)와 컴파일 오류의 한국어 메시지
4. expand_args(spec.derived)·eval_len(spec.ret.len)
5. 성능: for (int i = 0; i < 1000000; i++) s += i; (목표 2초 이하)
실패가 하나라도 있으면 종료 코드 1. gcc가 필요하다.
"""
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src', 'grader'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import cinterp  # noqa: E402
import cref  # noqa: E402
import harness  # noqa: E402

GCC_FLAGS = ['-O0', '-fsanitize=address,undefined', '-w']
ENV = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:symbolize=0', UBSAN_OPTIONS='print_stacktrace=0')
H = '#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#include <stdbool.h>\n#include <ctype.h>\n#include <math.h>\n#include <limits.h>\n'

# ---------------------------------------------------------------- 1. gcc와 출력 비교
PROGRAMS = [
    ('배열 합·최댓값·최솟값', r'''
int main(void) {
    int a[] = {5, -3, 12, 7, 0, 12, -8};
    int n = sizeof(a) / sizeof(a[0]);
    int s = 0, mx = a[0], mn = a[0], mi = 0;
    for (int i = 0; i < n; i++) {
        s += a[i];
        if (a[i] > mx) { mx = a[i]; mi = i; }
        if (a[i] < mn) mn = a[i];
    }
    printf("n=%d sum=%d max=%d at %d min=%d avg=%.3f\n", n, s, mx, mi, mn, (double)s / n);
    return 0;
}'''),
    ('2차원 배열 행·열 합', r'''
int main(void) {
    int b[3][4] = {{1, 2, 3, 4}, {5, 6, 7, 8}, {9, 10, 11, 12}};
    for (int i = 0; i < 3; i++) {
        int r = 0;
        for (int j = 0; j < 4; j++) r += b[i][j];
        printf("row%d=%d ", i, r);
    }
    for (int j = 0; j < 4; j++) {
        int c = 0;
        for (int i = 0; i < 3; i++) c += b[i][j];
        printf("col%d=%d ", j, c);
    }
    int d[2][3] = {1, 2, 3, 4};
    printf("\n%d %d %d %zu %zu\n", d[1][0], d[1][1], d[1][2], sizeof(b), sizeof(b[0]));
    return 0;
}'''),
    ('문자열 strlen·strcpy·strcat·strcmp', r'''
int main(void) {
    char a[32] = "hello";
    char b[32];
    strcpy(b, a);
    strcat(b, ", world");
    printf("%s %zu %zu\n", b, strlen(a), strlen(b));
    printf("%d %d %d %d\n", strcmp(a, "hello") == 0, strcmp("abc", "abd") < 0, strcmp("b", "a") > 0, strcmp("ab", "abc") < 0);
    printf("%d %d %d\n", strcmp("abc", "abd"), strcmp("abd", "abc"), strncmp("abcx", "abcy", 3));
    char c[10];
    strncpy(c, "abcdef", 3);
    c[3] = '\0';
    strncat(c, "XYZW", 2);
    printf("[%s] %d\n", c, (int)strlen(c));
    return 0;
}'''),
    ('대소문자 바꾸기·ctype', r'''
int main(void) {
    char s[] = "Hello, World 123!";
    int up = 0, lo = 0, dg = 0, sp = 0, pu = 0;
    for (int i = 0; s[i] != '\0'; i++) {
        if (isupper(s[i])) { up++; s[i] = tolower(s[i]); }
        else if (islower(s[i])) { lo++; s[i] = toupper(s[i]); }
        if (isdigit(s[i])) dg++;
        if (isspace(s[i])) sp++;
        if (ispunct(s[i])) pu++;
    }
    printf("%s %d %d %d %d %d\n", s, up, lo, dg, sp, pu);
    printf("%d %d %d %d\n", isdigit('7'), isalpha('Q'), isalnum('_'), toupper('z'));
    for (char c = 'a'; c <= 'e'; c++) putchar(c - 'a' + 'A');
    putchar('\n');
    return 0;
}'''),
    ('문자열 뒤집기·회문', r'''
int is_pal(const char *s) {
    int n = strlen(s);
    for (int i = 0; i < n / 2; i++)
        if (s[i] != s[n - 1 - i]) return 0;
    return 1;
}
int main(void) {
    char s[] = "abcdef";
    int n = strlen(s);
    for (int i = 0, j = n - 1; i < j; i++, j--) {
        char t = s[i]; s[i] = s[j]; s[j] = t;
    }
    printf("%s %d %d %d\n", s, is_pal("level"), is_pal("ab"), is_pal(""));
    return 0;
}'''),
    ('malloc 배열 만들어 돌려주기', r'''
int *make(int n) {
    int *p = (int *)malloc(sizeof(int) * n);
    for (int i = 0; i < n; i++) p[i] = i * i;
    return p;
}
int main(void) {
    int *a = make(6);
    for (int i = 0; i < 6; i++) printf("%d ", a[i]);
    free(a);
    int *z = calloc(4, sizeof(int));
    printf("| %d %d\n", z[0], z[3]);
    z = realloc(z, 8 * sizeof(int));
    z[7] = 99;
    printf("%d %d\n", z[3], z[7]);
    free(z);
    return 0;
}'''),
    ('구조체 배열 정렬(버블)', r'''
typedef struct {
    char name[12];
    int score;
} Student;
int main(void) {
    Student s[5] = {{"kim", 80}, {"lee", 95}, {"park", 70}, {"choi", 95}, {"jung", 88}};
    for (int i = 0; i < 5; i++)
        for (int j = 0; j < 4 - i; j++)
            if (s[j].score < s[j + 1].score) {
                Student t = s[j]; s[j] = s[j + 1]; s[j + 1] = t;
            }
    for (int i = 0; i < 5; i++) printf("%s:%d ", s[i].name, s[i].score);
    printf("\n%zu\n", sizeof(Student));
    return 0;
}'''),
    ('qsort 정수·구조체·문자열', r'''
typedef struct { int id; double w; } Item;
int asc(const void *a, const void *b) { return *(const int *)a - *(const int *)b; }
int desc(const void *a, const void *b) { return *(int *)b - *(int *)a; }
int byw(const void *a, const void *b) {
    const Item *x = a, *y = b;
    if (x->w < y->w) return -1;
    if (x->w > y->w) return 1;
    return x->id - y->id;
}
int bystr(const void *a, const void *b) { return strcmp(*(char **)a, *(char **)b); }
int main(void) {
    int a[] = {5, 2, 9, 1, 5, 6, -3};
    qsort(a, 7, sizeof(int), asc);
    for (int i = 0; i < 7; i++) printf("%d ", a[i]);
    qsort(a, 7, sizeof a[0], desc);
    for (int i = 0; i < 7; i++) printf("%d ", a[i]);
    Item it[4] = {{1, 2.5}, {2, 0.5}, {3, 2.5}, {4, 1.0}};
    qsort(it, 4, sizeof(Item), byw);
    for (int i = 0; i < 4; i++) printf("(%d %.1f)", it[i].id, it[i].w);
    char *w[] = {"pear", "apple", "fig", "banana"};
    qsort(w, 4, sizeof(char *), bystr);
    for (int i = 0; i < 4; i++) printf(" %s", w[i]);
    printf("\n");
    return 0;
}'''),
    ('재귀: 팩토리얼·피보나치·최대공약수·하노이', r'''
long long fact(int n) { return n <= 1 ? 1 : n * fact(n - 1); }
int fib(int n) { if (n < 2) return n; return fib(n - 1) + fib(n - 2); }
int gcd(int a, int b) { return b == 0 ? a : gcd(b, a % b); }
int hanoi(int n) { if (n == 0) return 0; return 2 * hanoi(n - 1) + 1; }
int sum_arr(int *a, int n) { return n == 0 ? 0 : a[n - 1] + sum_arr(a, n - 1); }
int depth(int n) { return n == 0 ? 0 : 1 + depth(n - 1); }
int main(void) {
    int a[] = {3, 1, 4, 1, 5};
    printf("%lld %d %d %d %d %d\n", fact(20), fib(20), gcd(84, 36), hanoi(10), sum_arr(a, 5), depth(1500));
    return 0;
}'''),
    ('음수 나눗셈·나머지', r'''
int main(void) {
    int v[][2] = {{7, 2}, {-7, 2}, {7, -2}, {-7, -2}, {0, 5}, {-1, 3}};
    for (int i = 0; i < 6; i++) printf("%d/%d=%d %d%%%d=%d\n", v[i][0], v[i][1], v[i][0] / v[i][1], v[i][0], v[i][1], v[i][0] % v[i][1]);
    long long x = -9000000000LL;
    printf("%lld %lld %d\n", x / 7, x % 7, -17 / 5 * 5 + -17 % 5);
    return 0;
}'''),
    ('부호 없는 수 감소·비교', r'''
int main(void) {
    unsigned int u = 0;
    u--;
    printf("%u %d\n", u, u > 5);
    size_t n = 3;
    int cnt = 0;
    for (size_t i = n; i-- > 0;) cnt++;
    printf("%d %zu\n", cnt, n - 5);
    printf("%d %d\n", -1 < 1u, (unsigned char)300);
    unsigned short us = 65535;
    us++;
    printf("%u %u\n", us, (unsigned)(-1) / 2);
    return 0;
}'''),
    ('char 산술', r'''
int main(void) {
    char c = 'a';
    c += 2;
    char d = c + 1;
    int k = '9' - '0';
    char over = (char)200;
    printf("%c %c %d %d %d %d\n", c, d, k, over, 'A' + 1, (char)('z' + 10));
    char s[] = "3172";
    int num = 0;
    for (int i = 0; s[i]; i++) num = num * 10 + (s[i] - '0');
    printf("%d %c%c\n", num, 'a' + 25, '0' + 7);
    return 0;
}'''),
    ('printf 서식', r'''
int main(void) {
    printf("[%5d][%-5d][%05d][%+d][% d][%x][%X][%o][%#x][%#o]\n", 42, 42, 42, 42, 42, 255, 255, 8, 255, 8);
    printf("[%f][%.2f][%10.3f][%-10.1f][%e][%E][%g][%g][%g][%.3g]\n", 3.14159, 3.14159, 2.5, 2.5, 12345.678, 0.00012, 100000.0, 1000000.0, 0.0001, 3.14159);
    printf("[%c][%3c][%-3c][%s][%8s][%-8s][%.2s][%%]\n", 'A', 'B', 'C', "abc", "abc", "abc", "abc");
    printf("[%ld][%lld][%lu][%zu][%hd][%hhd][%llu]\n", 123456789012L, -9000000000LL, 18446744073709551615UL, sizeof(double), (short)70000, (char)300, 12345678901234ULL);
    printf("[%*d][%-*d][%.*f][%lf][%5.1lf]\n", 6, 7, 6, 7, 2, 1.23456, 2.0, 9.87);
    printf("[%.0f][%.0f][%.0f][%.1f][%g][%g]\n", 0.5, 1.5, 2.5, -0.0, 1e-5, 123456789.0);
    int n = printf("count\n");
    printf("%d\n", n);
    return 0;
}'''),
    ('switch fall-through', r'''
int f(int x) {
    int r = 0;
    switch (x) {
    case 1: r += 1;
    case 2: r += 10;
        break;
    case 3:
    case 4: r += 100;
    default: r += 1000;
    case 5: r += 5;
    }
    return r;
}
int main(void) {
    for (int i = 0; i <= 6; i++) printf("%d ", f(i));
    char g = 'B';
    switch (g) { case 'A': printf("a"); break; case 'B': printf("b"); case 'C': printf("c"); break; }
    printf("\n");
    return 0;
}'''),
    ('비트 연산', r'''
int popcount(unsigned x) { int c = 0; while (x) { c += x & 1; x >>= 1; } return c; }
int main(void) {
    int a = 0x5A, b = 0x0F;
    printf("%d %d %d %d %d %d\n", a & b, a | b, a ^ b, ~a, a << 3, a >> 2);
    printf("%d %d %d\n", -16 >> 2, -1 >> 31, 1 << 30);
    printf("%d %d %d\n", popcount(255), popcount(0x80000000u), (12 & (12 - 1)) == 0);
    unsigned int m = 0;
    for (int i = 0; i < 32; i += 3) m |= 1u << i;
    printf("%u %x %d\n", m, m, (m >> 4) & 7);
    return 0;
}'''),
    ('오버플로 감아 돌기(wrap)', r'''
int main(void) {
    int big = INT_MAX;
    big = big + 1;
    unsigned int ub = 4294967295u;
    ub = ub + 2;
    int m = 100000 * 100000;
    long long ok = 100000LL * 100000;
    short sh = (short)40000;
    printf("%d %u %d %lld %d %d\n", big, ub, m, ok, sh, (int)3000000000LL);
    printf("%d %d\n", INT_MIN, INT_MIN - 1);
    return 0;
}'''),
    ('반복문 break·continue·do-while', r'''
int main(void) {
    int s = 0;
    for (int i = 0; i < 100; i++) {
        if (i % 3 == 0) continue;
        if (i > 20) break;
        s += i;
    }
    int k = 0, w = 1;
    while (1) { w *= 2; if (++k == 10) break; }
    int d = 5;
    do { d--; } while (d > 0);
    int e = 0;
    do e++; while (0);
    for (int i = 0; i < 3; i++) for (int j = 0; j < 3; j++) { if (j == i) continue; if (j > 1) break; s += 100; }
    printf("%d %d %d %d %d\n", s, k, w, d, e);
    return 0;
}'''),
    ('삼항·쉼표·복합 대입', r'''
int main(void) {
    int a = 5, b = 9;
    int mx = a > b ? a : b;
    double h = a > 3 ? 1.5 : 2;
    int c = (a++, b--, a + b);
    int x = 10;
    x += 3; x -= 1; x *= 4; x /= 3; x %= 7; x <<= 2; x >>= 1; x |= 1; x &= 7; x ^= 2;
    double y = 2.0;
    y *= 1.5; y /= 4; y -= 0.25; y += 10;
    printf("%d %.1f %d %d %d %d %.4f\n", mx, h, a, b, c, x, y);
    int i = 5, j = i++ + ++i;
    printf("%d %d\n", i, j);
    return 0;
}'''),
    ('포인터: swap·산술·차이', r'''
void swap(int *x, int *y) { int t = *x; *x = *y; *y = t; }
int main(void) {
    int a = 1, b = 2;
    swap(&a, &b);
    int arr[] = {10, 20, 30, 40, 50};
    int *p = arr, *q = &arr[4];
    p++;
    *(p + 1) = 33;
    printf("%d %d %d %d %ld %d\n", a, b, *p, arr[2], (long)(q - p), *q - *arr);
    int *r = arr + 4;
    int sum = 0;
    while (r >= arr) { sum += *r; r--; if (r < arr) break; }
    int **pp = &p;
    **pp = 21;
    printf("%d %d %d\n", sum, arr[1], p == &arr[1]);
    return 0;
}'''),
    ('전역 변수·static 지역 변수', r'''
int counter;
int total = 100;
int next_id(void) { static int id = 0; id++; return id; }
void bump(int k) { counter += k; total -= k; }
int main(void) {
    for (int i = 1; i <= 4; i++) bump(i);
    int a = next_id(), b = next_id(), c = next_id();
    printf("%d %d %d %d %d\n", counter, total, a, b, c);
    return 0;
}'''),
    ('enum·typedef', r'''
enum Color { RED, GREEN = 5, BLUE };
typedef enum { MON = 1, TUE, WED } Day;
typedef int score_t;
int main(void) {
    enum Color c = BLUE;
    Day d = WED;
    score_t s = 77;
    printf("%d %d %d %d %d\n", RED, GREEN, c, d, s);
    return 0;
}'''),
    ('구조체: 중첩·배열 필드·대입·값 반환', r'''
struct Point { int x, y; };
struct Rect { struct Point lt, rb; char tag[8]; };
struct Point mid(struct Point a, struct Point b) {
    struct Point m = {(a.x + b.x) / 2, (a.y + b.y) / 2};
    return m;
}
void move(struct Rect *r, int dx) { r->lt.x += dx; r->rb.x += dx; }
int main(void) {
    struct Rect r = {{0, 0}, {10, 6}, "box"};
    struct Rect r2 = r;
    move(&r2, 5);
    struct Point m = mid(r2.lt, r2.rb);
    r.tag[0] = 'B';
    printf("%d %d %d %d %s %s %zu\n", r2.lt.x, r2.rb.x, m.x, m.y, r.tag, r2.tag, sizeof(struct Rect));
    printf("%d\n", mid(r.lt, r.rb).y);
    return 0;
}'''),
    ('2차원 배열 매개변수 int b[][4]', r'''
int trace(int b[][4], int n) { int s = 0; for (int i = 0; i < n; i++) s += b[i][i]; return s; }
void fill(int b[][4], int rows) { for (int i = 0; i < rows; i++) for (int j = 0; j < 4; j++) b[i][j] = i * 4 + j; }
int main(void) {
    int b[4][4];
    fill(b, 4);
    printf("%d %d\n", trace(b, 4), b[3][2]);
    return 0;
}'''),
    ('int** 동적 2차원 배열', r'''
int main(void) {
    int n = 3, m = 4;
    int **g = malloc(n * sizeof(int *));
    for (int i = 0; i < n; i++) {
        g[i] = malloc(m * sizeof(int));
        for (int j = 0; j < m; j++) g[i][j] = (i + 1) * (j + 1);
    }
    int s = 0;
    for (int i = 0; i < n; i++) for (int j = 0; j < m; j++) s += g[i][j];
    printf("%d %d\n", s, g[2][3]);
    for (int i = 0; i < n; i++) free(g[i]);
    free(g);
    return 0;
}'''),
    ('atoi·sprintf로 숫자↔문자열', r'''
int main(void) {
    char buf[32];
    int n = sprintf(buf, "%d-%05.1f-%s", 42, 3.14159, "ok");
    printf("%s %d\n", buf, n);
    printf("%d %d %d %ld\n", atoi("123"), atoi("  -45xyz"), atoi("abc"), atol("9000000000"));
    char digits[16];
    sprintf(digits, "%d", 9075);
    int sum = 0;
    for (int i = 0; digits[i]; i++) sum += digits[i] - '0';
    printf("%s %d %zu\n", digits, sum, strlen(digits));
    return 0;
}'''),
    ('strchr·strrchr·strstr', r'''
int main(void) {
    const char *s = "banana split";
    char *a = strchr(s, 'n');
    char *b = strrchr(s, 'a');
    char *c = strstr(s, "spl");
    char *d = strstr(s, "xyz");
    printf("%ld %ld %ld %d %s\n", (long)(a - s), (long)(b - s), (long)(c - s), d == NULL, c);
    int cnt = 0;
    const char *p = s;
    while ((p = strchr(p, 'a')) != NULL) { cnt++; p++; }
    printf("%d\n", cnt);
    return 0;
}'''),
    ('memset·memcpy·memmove', r'''
int main(void) {
    int a[6];
    memset(a, 0, sizeof(a));
    int b[6] = {1, 2, 3, 4, 5, 6};
    memcpy(a, b, 3 * sizeof(int));
    int c[5];
    memset(c, -1, sizeof c);
    char s[16] = "abcdef";
    memmove(s + 2, s, 4);
    printf("%d %d %d %d %s\n", a[0], a[2], a[5], c[4], s);
    return 0;
}'''),
    ('수학 함수', r'''
int main(void) {
    printf("%.4f %.1f %.3f %.1f %.1f %.1f %.1f\n", sqrt(2.0), pow(2, 10), fabs(-3.25), floor(-2.5), ceil(-2.5), round(2.5), round(-2.5));
    printf("%.5f %.5f %.5f %.5f %d %d\n", log(10.0), exp(1.0), sin(1.0), cos(1.0), (int)sqrt(17), abs(-9));
    printf("%.2f %.2f %ld %lld\n", fmin(1.5, -2.0), fmax(1.5, -2.0), labs(-7L), llabs(-8LL));
    double d = 7.9, e = -7.9;
    printf("%d %d %d\n", (int)d, (int)e, (int)(d * 10) % 10);
    return 0;
}'''),
    ('float 정밀도·정수 승격', r'''
int main(void) {
    float f = 0.1f;
    float g = 1.0f / 3;
    double h = 1.0 / 3;
    float acc = 0;
    for (int i = 0; i < 10; i++) acc += 0.1f;
    printf("%.10f %.10f %.10f %.8f %d\n", f, g, h, acc, acc == 1.0f);
    unsigned char uc = 200;
    int r = uc + 100;
    char sc = -56;
    printf("%d %d %zu %zu %zu\n", r, sc + uc, sizeof(uc + 1), sizeof(f * 2), sizeof('a'));
    printf("%d %d\n", 7 / 2 * 2.0 == 6.0, (int)(2.9999999 + 0.0));
    return 0;
}'''),
    ('rand·srand', r'''
int main(void) {
    for (int i = 0; i < 3; i++) printf("%d ", rand());
    srand(42);
    for (int i = 0; i < 4; i++) printf("%d ", rand() % 100);
    srand(1);
    printf("%d\n", rand());
    return 0;
}'''),
    ('가변 길이 배열 int fibo[N + 1]', r'''
long long fibo(int N) {
    long long f[N + 1];
    f[0] = 0;
    if (N >= 1) f[1] = 1;
    for (int i = 2; i <= N; i++) f[i] = f[i - 1] + f[i - 2];
    return f[N];
}
int main(void) {
    int n = 5;
    int v[n * 2];
    for (int i = 0; i < n * 2; i++) v[i] = i * i;
    printf("%lld %lld %d %zu\n", fibo(10), fibo(80), v[9], sizeof(v));
    return 0;
}'''),
    ('2차원 가변 길이 배열 int a[n][m]', r'''
int grid(int n, int m) {
    int a[n][m];
    for (int i = 0; i < n; i++)
        for (int j = 0; j < m; j++)
            a[i][j] = i * 10 + j;
    int s = 0;
    for (int i = 0; i < n; i++) s += a[i][m - 1];
    return s * 1000 + (int)sizeof(a) + (int)sizeof(a[0]);
}
int main(void) {
    printf("%d %d\n", grid(3, 4), grid(2, 7));
    int r = 3;
    int dp[r + 1][r + 1];
    for (int i = 0; i <= r; i++) for (int j = 0; j <= r; j++) dp[i][j] = (i == 0 || j == 0) ? 1 : dp[i - 1][j] + dp[i][j - 1];
    printf("%d\n", dp[r][r]);
    return 0;
}'''),
    ('INT_MIN·INT_MAX 최댓값 찾기', r'''
int main(void) {
    int a[] = {-7, -3, -9};
    int best = INT_MIN, worst = INT_MAX;
    for (int i = 0; i < 3; i++) {
        if (a[i] > best) best = a[i];
        if (a[i] < worst) worst = a[i];
    }
    printf("%d %d %d %d %lld %lld\n", best, worst, INT_MAX, INT_MIN, LLONG_MAX, LLONG_MIN);
    printf("%u %d %d\n", UINT_MAX, CHAR_MAX, SHRT_MIN);
    return 0;
}'''),
    ('long long 큰 수(5×10^11)', r'''
long long tri(long long N) { return N * (N + 1) / 2 % 1000000007LL; }
int main(void) {
    long long N = 500000000000LL;
    long long sq = N / 1000 * (N / 1000);
    printf("%lld %lld %lld %lld\n", N, sq, tri(N), N % 9973);
    unsigned long long u = 18446744073709551615ULL;
    printf("%llu %llu\n", u, u + 2);
    return 0;
}'''),
    ('sizeof와 구조체 정렬(패딩)', r'''
struct A { char c; int i; };
struct B { char c; double d; char e; };
struct C { short s; char c[3]; };
int main(void) {
    printf("%zu %zu %zu %zu %zu %zu %zu %zu %zu\n", sizeof(char), sizeof(short), sizeof(int), sizeof(long), sizeof(long long), sizeof(float), sizeof(double), sizeof(int *), sizeof(size_t));
    printf("%zu %zu %zu\n", sizeof(struct A), sizeof(struct B), sizeof(struct C));
    int arr[7];
    printf("%zu %zu\n", sizeof arr, sizeof arr / sizeof arr[0]);
    return 0;
}'''),
    ('이스케이프·문자열 상수 이어 붙이기', r'''
int main(void) {
    const char *s = "tab\there" " and " "quote\"\\";
    printf("%s|%zu\n", s, strlen(s));
    printf("%d %d %d %d\n", '\n', '\0', '\x41', '\101');
    char k[] = "가나";
    printf("%zu %s\n", strlen(k), k);
    return 0;
}'''),
    ('char 배열 초기화와 수정', r'''
int main(void) {
    char a[10] = "hi";
    char b[] = {'x', 'y', 'z', '\0'};
    char c[5] = {0};
    a[2] = '!';
    a[3] = '\0';
    c[0] = 'Q';
    printf("%s %s %s %zu %zu\n", a, b, c, sizeof(a), sizeof(b));
    return 0;
}'''),
    ('연결 리스트(malloc)', r'''
typedef struct Node { int v; struct Node *next; } Node;
Node *push(Node *head, int v) { Node *n = malloc(sizeof(Node)); n->v = v; n->next = head; return n; }
int main(void) {
    Node *h = NULL;
    for (int i = 1; i <= 5; i++) h = push(h, i * 3);
    int s = 0;
    for (Node *p = h; p != NULL; p = p->next) { printf("%d ", p->v); s += p->v; }
    while (h) { Node *t = h->next; free(h); h = t; }
    printf("| %d\n", s);
    return 0;
}'''),
    ('정렬: 선택·삽입', r'''
void sel(int *a, int n) {
    for (int i = 0; i < n - 1; i++) {
        int m = i;
        for (int j = i + 1; j < n; j++) if (a[j] < a[m]) m = j;
        int t = a[i]; a[i] = a[m]; a[m] = t;
    }
}
void ins(int a[], int n) {
    for (int i = 1; i < n; i++) {
        int k = a[i], j = i - 1;
        while (j >= 0 && a[j] > k) { a[j + 1] = a[j]; j--; }
        a[j + 1] = k;
    }
}
int main(void) {
    int a[] = {9, 4, 7, 1, 8, 2}, b[] = {3, -1, 3, 0, 10};
    sel(a, 6);
    ins(b, 5);
    for (int i = 0; i < 6; i++) printf("%d ", a[i]);
    for (int i = 0; i < 5; i++) printf("%d ", b[i]);
    printf("\n");
    return 0;
}'''),
    ('이진 탐색', r'''
int bs(const int *a, int n, int x) {
    int lo = 0, hi = n - 1;
    while (lo <= hi) {
        int mid = lo + (hi - lo) / 2;
        if (a[mid] == x) return mid;
        if (a[mid] < x) lo = mid + 1; else hi = mid - 1;
    }
    return -1;
}
int main(void) {
    int a[] = {1, 3, 5, 7, 9, 11, 13};
    printf("%d %d %d %d\n", bs(a, 7, 7), bs(a, 7, 1), bs(a, 7, 13), bs(a, 7, 4));
    return 0;
}'''),
    ('소수 체(에라토스테네스)', r'''
int main(void) {
    int n = 100;
    bool comp[101] = {false};
    int cnt = 0, last = 0;
    for (int i = 2; i <= n; i++) {
        if (comp[i]) continue;
        cnt++; last = i;
        for (int j = i * i; j <= n; j += i) comp[j] = true;
    }
    printf("%d %d %d %zu\n", cnt, last, comp[91], sizeof(bool));
    return 0;
}'''),
    ('글자 빈도(int cnt[26])', r'''
int main(void) {
    const char *s = "the quick brown fox jumps over the lazy dog";
    int cnt[26] = {0};
    for (int i = 0; s[i]; i++) if (s[i] >= 'a' && s[i] <= 'z') cnt[s[i] - 'a']++;
    int best = 0;
    for (int i = 1; i < 26; i++) if (cnt[i] > cnt[best]) best = i;
    printf("%c %d %d %d\n", 'a' + best, cnt[best], cnt['z' - 'a'], cnt[4]);
    return 0;
}'''),
    ('행렬 곱셈', r'''
int main(void) {
    int A[2][3] = {{1, 2, 3}, {4, 5, 6}}, B[3][2] = {{7, 8}, {9, 10}, {11, 12}}, C[2][2] = {{0}};
    for (int i = 0; i < 2; i++) for (int j = 0; j < 2; j++) for (int k = 0; k < 3; k++) C[i][j] += A[i][k] * B[k][j];
    printf("%d %d %d %d\n", C[0][0], C[0][1], C[1][0], C[1][1]);
    return 0;
}'''),
    ('단어 세기(공백 나누기)', r'''
int main(void) {
    char s[] = "  hello   big world  ";
    int words = 0, in = 0, longest = 0, cur = 0;
    for (int i = 0; s[i] != '\0'; i++) {
        if (s[i] == ' ') { in = 0; cur = 0; }
        else { if (!in) words++; in = 1; cur++; if (cur > longest) longest = cur; }
    }
    printf("%d %d\n", words, longest);
    return 0;
}'''),
    ('배열로 만든 스택', r'''
int st[100], top = -1;
void push(int v) { st[++top] = v; }
int pop(void) { return st[top--]; }
int main(void) {
    const char *e = "((a)(b(c)))";
    int ok = 1, maxd = 0;
    for (int i = 0; e[i]; i++) {
        if (e[i] == '(') { push(i); if (top + 1 > maxd) maxd = top + 1; }
        else if (e[i] == ')') { if (top < 0) { ok = 0; break; } pop(); }
    }
    printf("%d %d %d\n", ok && top == -1, maxd, top);
    return 0;
}'''),
    ('const 포인터', r'''
int sum(const int *a, int n) { int s = 0; for (int i = 0; i < n; i++) s += a[i]; return s; }
int main(void) {
    const int a[] = {4, 5, 6};
    const char *msg = "const";
    int x = 3;
    int *const px = &x;
    *px = 8;
    printf("%d %s %d\n", sum(a, 3), msg, x);
    return 0;
}'''),
    ('함수 포인터 배열', r'''
int add(int a, int b) { return a + b; }
int sub(int a, int b) { return a - b; }
int mul(int a, int b) { return a * b; }
int apply(int (*f)(int, int), int a, int b) { return f(a, b); }
int main(void) {
    int (*ops[3])(int, int) = {add, sub, mul};
    for (int i = 0; i < 3; i++) printf("%d ", ops[i](7, 3));
    int (*g)(int, int) = &mul;
    printf("%d %d\n", apply(sub, 10, 4), (*g)(6, 7));
    return 0;
}'''),
    ('실수 → 정수 캐스트(버림)', r'''
int main(void) {
    double v[] = {2.7, -2.7, 0.5, -0.5, 1e9, 3.999999};
    for (int i = 0; i < 6; i++) printf("%d ", (int)v[i]);
    int a = 7, b = 2;
    double q = a / b, r = (double)a / b;
    printf("%.1f %.1f %d\n", q, r, (int)(r * 2));
    return 0;
}'''),
    ('문자열 배열 strcmp 정렬', r'''
int main(void) {
    char names[5][10] = {"mango", "apple", "kiwi", "banana", "apple"};
    for (int i = 0; i < 4; i++)
        for (int j = 0; j < 4 - i; j++)
            if (strcmp(names[j], names[j + 1]) > 0) {
                char t[10];
                strcpy(t, names[j]); strcpy(names[j], names[j + 1]); strcpy(names[j + 1], t);
            }
    for (int i = 0; i < 5; i++) printf("%s ", names[i]);
    printf("%zu\n", sizeof(names));
    return 0;
}'''),
    ('자릿수 합·뒤집기', r'''
int main(void) {
    int n = 98765, s = 0, rev = 0;
    while (n > 0) { s += n % 10; rev = rev * 10 + n % 10; n /= 10; }
    printf("%d %d\n", s, rev);
    int neg = -1234, ds = 0;
    while (neg != 0) { ds += neg % 10; neg /= 10; }
    printf("%d\n", ds);
    return 0;
}'''),
    ('시프트: 음수 오른쪽·이진수 문자열', r'''
int main(void) {
    int x = -100;
    printf("%d %d %u\n", x >> 1, x >> 4, (unsigned)x >> 28);
    char bin[33];
    unsigned v = 37;
    int k = 0;
    if (v == 0) bin[k++] = '0';
    while (v) { bin[k++] = '0' + (v & 1); v >>= 1; }
    bin[k] = '\0';
    for (int i = 0, j = k - 1; i < j; i++, j--) { char t = bin[i]; bin[i] = bin[j]; bin[j] = t; }
    printf("%s\n", bin);
    return 0;
}'''),
    ('구조체 포인터로 갱신', r'''
typedef struct { char name[16]; int hp; int lv; } Hero;
void hit(Hero *h, int d) { h->hp -= d; if (h->hp < 0) h->hp = 0; }
void level(Hero hs[], int n) { for (int i = 0; i < n; i++) if (hs[i].hp > 50) hs[i].lv++; }
int main(void) {
    Hero hs[3] = {{"A", 100, 1}, {"B", 40, 2}, {"C", 70, 3}};
    hit(&hs[0], 30); hit(hs + 2, 25); hit(&hs[1], 100);
    level(hs, 3);
    for (int i = 0; i < 3; i++) printf("%s %d %d / ", hs[i].name, hs[i].hp, hs[i].lv);
    Hero *p = &hs[2];
    p->name[0] = 'Z';
    printf("%s %c\n", (*p).name, hs[2].name[0]);
    return 0;
}'''),
    ('puts·putchar', r'''
int main(void) {
    puts("line one");
    putchar('x'); putchar(10);
    int r = puts("");
    printf("%d\n", r > 0);
    return 0;
}'''),
    ('지정 초기화·괄호 생략', r'''
struct P { int x, y, z; };
int main(void) {
    int a[6] = {[2] = 5, [4] = 9};
    struct P p = {.z = 3, .x = 1};
    struct P ps[2] = {1, 2, 3, 4};
    int m[2][2][2] = {1, 2, 3, 4, 5, 6, 7};
    printf("%d %d %d %d %d %d %d %d %d\n", a[0], a[2], a[4], p.x, p.y, p.z, ps[1].x, ps[1].z, m[1][1][1] + m[1][0][1]);
    return 0;
}'''),
    ('static 배열이 호출 사이에 남음', r'''
int memo(int n) {
    static int cache[50];
    if (n < 2) return n;
    if (cache[n]) return cache[n];
    return cache[n] = memo(n - 1) + memo(n - 2);
}
int main(void) {
    printf("%d %d\n", memo(40), memo(45));
    return 0;
}'''),
    ('realloc으로 늘리기', r'''
int main(void) {
    int cap = 2, n = 0;
    int *a = malloc(cap * sizeof(int));
    for (int i = 0; i < 20; i++) {
        if (n == cap) { cap *= 2; a = realloc(a, cap * sizeof(int)); }
        a[n++] = i * 3;
    }
    int s = 0;
    for (int i = 0; i < n; i++) s += a[i];
    printf("%d %d %d\n", n, cap, s);
    free(a);
    return 0;
}'''),
    ('bool과 비교 결과', r'''
bool even(int x) { return x % 2 == 0; }
int main(void) {
    bool t = true, f = false;
    bool b = 5;
    int c = (3 > 2) + (2 > 3) + !0 + !7;
    printf("%d %d %d %d %d %d\n", t, f, b, even(4), even(-3), c);
    return 0;
}'''),
    ('삼항 혼합 타입·조건 연쇄', r'''
const char *grade(int s) { return s >= 90 ? "A" : s >= 80 ? "B" : s >= 70 ? "C" : "F"; }
int main(void) {
    int n = 3;
    double d = n > 2 ? n / 2 : 0.5;
    printf("%s%s%s%s %.2f\n", grade(95), grade(85), grade(72), grade(10), d);
    return 0;
}'''),
    ('윤년·날짜 계산', r'''
int leap(int y) { return (y % 4 == 0 && y % 100 != 0) || y % 400 == 0; }
int main(void) {
    int days[] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
    int y = 2024, m = 3, d = 1, doy = d;
    for (int i = 0; i < m - 1; i++) doy += days[i] + (i == 1 && leap(y));
    printf("%d %d %d %d %d\n", leap(1900), leap(2000), leap(2024), leap(2023), doy);
    return 0;
}'''),
    ('main의 return 값(종료 코드)', r'''
int main(void) {
    printf("exit with 3\n");
    return 3;
}'''),
    ('exit 함수', r'''
void check(int v) { if (v < 0) { printf("negative!\n"); exit(2); } }
int main(void) {
    check(5);
    check(-1);
    printf("not here\n");
    return 0;
}'''),
    ('#define 상수·조건부', r'''
#define N 5
#define MSG "items"
#define DEBUG
int main(void) {
    int a[N];
    for (int i = 0; i < N; i++) a[i] = i * N;
#ifdef DEBUG
    printf("debug ");
#else
    printf("release ");
#endif
    printf("%d %s\n", a[N - 1], MSG);
    return 0;
}'''),
    ('큰 반복(1부터 n까지 합·약수 개수)', r'''
int main(void) {
    long long s = 0;
    for (int i = 1; i <= 200000; i++) s += i % 7 == 0 ? i : 0;
    int n = 360, cnt = 0;
    for (int i = 1; i * i <= n; i++) if (n % i == 0) cnt += (i * i == n) ? 1 : 2;
    printf("%lld %d\n", s, cnt);
    return 0;
}'''),
    ('포인터로 문자열 순회·복사', r'''
void my_copy(char *d, const char *s) { while ((*d++ = *s++) != '\0'); }
int my_len(const char *s) { const char *p = s; while (*p) p++; return p - s; }
int main(void) {
    char buf[20];
    my_copy(buf, "pointer");
    char *e = buf + my_len(buf) - 1;
    printf("%s %d %c %c\n", buf, my_len(buf), *e, *(buf + 2));
    return 0;
}'''),
    ('unsigned char 배열·바이트', r'''
int main(void) {
    unsigned char b[4] = {250, 251, 252, 253};
    int s = 0;
    for (int i = 0; i < 4; i++) { b[i] += 10; s += b[i]; }
    unsigned int x = 0x12345678;
    unsigned char *p = (unsigned char *)&x;
    printf("%d %d %x %x\n", s, b[3], p[0], p[3]);
    return 0;
}'''),
]

PROGRAMS += [
    ('배열 포인터 int (*p)[4]', r'''
int main(void) {
    int b[3][4] = {{1, 2, 3, 4}, {5, 6, 7, 8}, {9, 10, 11, 12}};
    int (*p)[4] = b;
    p++;
    int *q = *p;
    printf("%d %d %d %zu %d\n", p[0][2], (*p)[3], q[1], sizeof(*p), *(*(b + 2) + 1));
    return 0;
}'''),
    ('문자열 포인터 배열 순회', r'''
int main(void) {
    const char *words[] = {"alpha", "beta", "gamma", NULL};
    const char **pp = words;
    int total = 0;
    while (*pp) { total += strlen(*pp); printf("%c", **pp); pp++; }
    printf(" %d %c\n", total, words[2][4]);
    return 0;
}'''),
    ('union', r'''
union U { int i; unsigned char b[4]; float f; };
int main(void) {
    union U u;
    u.i = 0x01020304;
    printf("%d %d %zu\n", u.b[0], u.b[3], sizeof(union U));
    u.f = 1.0f;
    printf("%x\n", u.i);
    return 0;
}'''),
    ('단락 평가(&& ||) 부작용', r'''
int cnt = 0;
int t(int v) { cnt++; return v; }
int main(void) {
    int a[3] = {1, 2, 3};
    int i = 3;
    if (i < 3 && a[i] > 0) printf("no");
    int r = t(0) && t(1);
    int s = t(1) || t(0);
    int u = t(0) || t(0) || t(1);
    printf("%d %d %d %d\n", r, s, u, cnt);
    return 0;
}'''),
    ('do-while continue·switch 안 continue', r'''
int main(void) {
    int i = 0, s = 0;
    do { i++; if (i % 2) continue; s += i; } while (i < 10);
    int t = 0;
    for (int k = 0; k < 6; k++) {
        switch (k % 3) {
        case 0: continue;
        case 1: t += 10; break;
        default: t += 1;
        }
        t += 100;
    }
    printf("%d %d %d\n", i, s, t);
    return 0;
}'''),
    ('함수 원형 먼저·static 함수', r'''
static int helper(int x);
int twice(int);
int main(void) { printf("%d %d\n", helper(5), twice(21)); return 0; }
static int helper(int x) { return x * x + twice(x); }
int twice(int v) { return v * 2; }
'''),
    ('병합 정렬(malloc 임시 배열)', r'''
void merge_sort(int *a, int lo, int hi, int *tmp) {
    if (hi - lo < 2) return;
    int mid = (lo + hi) / 2;
    merge_sort(a, lo, mid, tmp);
    merge_sort(a, mid, hi, tmp);
    int i = lo, j = mid, k = lo;
    while (i < mid && j < hi) tmp[k++] = a[i] <= a[j] ? a[i++] : a[j++];
    while (i < mid) tmp[k++] = a[i++];
    while (j < hi) tmp[k++] = a[j++];
    for (k = lo; k < hi; k++) a[k] = tmp[k];
}
int main(void) {
    int a[] = {38, 27, 43, 3, 9, 82, 10, 3, -5, 0};
    int n = 10;
    int *tmp = malloc(n * sizeof *tmp);
    merge_sort(a, 0, n, tmp);
    for (int i = 0; i < n; i++) printf("%d ", a[i]);
    free(tmp);
    printf("\n");
    return 0;
}'''),
    ('퀵 정렬(재귀)', r'''
void swap(int *a, int *b) { int t = *a; *a = *b; *b = t; }
int part(int a[], int lo, int hi) {
    int p = a[hi], i = lo - 1;
    for (int j = lo; j < hi; j++) if (a[j] < p) swap(&a[++i], &a[j]);
    swap(&a[i + 1], &a[hi]);
    return i + 1;
}
void qs(int a[], int lo, int hi) { if (lo < hi) { int p = part(a, lo, hi); qs(a, lo, p - 1); qs(a, p + 1, hi); } }
int main(void) {
    int a[12];
    unsigned x = 12345;
    for (int i = 0; i < 12; i++) { x = x * 1103515245u + 12345u; a[i] = (x >> 16) % 100; }
    qs(a, 0, 11);
    for (int i = 0; i < 12; i++) printf("%d ", a[i]);
    printf("\n");
    return 0;
}'''),
    ('격자 BFS(큐 배열)', r'''
int main(void) {
    char g[5][6] = {"S..#.", ".#...", ".#.#.", "...#E", "##..."};
    int dist[5][5];
    for (int i = 0; i < 5; i++) for (int j = 0; j < 5; j++) dist[i][j] = -1;
    int qr[25], qc[25], h = 0, t = 0;
    qr[t] = 0; qc[t++] = 0; dist[0][0] = 0;
    int dr[4] = {1, -1, 0, 0}, dc[4] = {0, 0, 1, -1};
    while (h < t) {
        int r = qr[h], c = qc[h++];
        for (int d = 0; d < 4; d++) {
            int nr = r + dr[d], nc = c + dc[d];
            if (nr < 0 || nr >= 5 || nc < 0 || nc >= 5) continue;
            if (g[nr][nc] == '#' || dist[nr][nc] != -1) continue;
            dist[nr][nc] = dist[r][c] + 1;
            qr[t] = nr; qc[t++] = nc;
        }
    }
    printf("%d %d\n", dist[3][4], t);
    return 0;
}'''),
    ('오버플로 검사 패턴·1ULL << 63', r'''
int main(void) {
    int a = 2000000000, b = 2000000000;
    if (a > INT_MAX - b) printf("overflow ");
    unsigned long long top = 1ULL << 63;
    long long mn = LLONG_MIN;
    printf("%llu %lld %d\n", top, mn, (int)(top >> 60));
    return 0;
}'''),
    ('대입이 조건 안에·연쇄 대입', r'''
int main(void) {
    const char *s = "abc,de,,f";
    char c;
    int i = 0, commas = 0;
    while ((c = s[i++]) != '\0') if (c == ',') commas++;
    int a, b, d;
    a = b = d = 7;
    a += b -= 2;
    int n = 5, steps = 0;
    while (n--) steps++;
    printf("%d %d %d %d %d %d\n", commas, i, a, b, steps, n);
    return 0;
}'''),
    ('!! · 단항 + · 16진·8진 상수', r'''
int main(void) {
    int x = 42;
    printf("%d %d %d %d %d %d\n", !!x, !!0, +x, -(-x), 0x1F + 010, '\'' + '\\');
    return 0;
}'''),
    ('전역 문자열 배열·const 표', r'''
const char *days[] = {"Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"};
const int mdays[12] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
int main(void) {
    int total = 0;
    for (int i = 0; i < 12; i++) total += mdays[i];
    printf("%s %s %d %zu\n", days[0], days[6], total, sizeof(days) / sizeof(days[0]));
    return 0;
}'''),
    ('enum과 switch', r'''
typedef enum { ROCK, PAPER, SCISSORS } Hand;
int beats(Hand a, Hand b) {
    switch (a) {
    case ROCK: return b == SCISSORS;
    case PAPER: return b == ROCK;
    case SCISSORS: return b == PAPER;
    }
    return 0;
}
int main(void) {
    int w = 0;
    for (int a = 0; a < 3; a++) for (int b = 0; b < 3; b++) w += beats(a, b) * (a * 3 + b);
    printf("%d\n", w);
    return 0;
}'''),
    ('백트래킹: 순열', r'''
int n = 4, used[5], perm[5], count = 0;
char out[64];
int pos = 0;
void go(int d) {
    if (d == n) {
        count++;
        if (count <= 3) { for (int i = 0; i < n; i++) out[pos++] = '0' + perm[i]; out[pos++] = ' '; }
        return;
    }
    for (int i = 1; i <= n; i++) {
        if (used[i]) continue;
        used[i] = 1; perm[d] = i;
        go(d + 1);
        used[i] = 0;
    }
}
int main(void) { go(0); out[pos] = 0; printf("%d %s\n", count, out); return 0; }'''),
    ('DP: LCS', r'''
int lcs(const char *a, const char *b) {
    int n = strlen(a), m = strlen(b);
    int dp[n + 1][m + 1];
    for (int i = 0; i <= n; i++)
        for (int j = 0; j <= m; j++) {
            if (i == 0 || j == 0) dp[i][j] = 0;
            else if (a[i - 1] == b[j - 1]) dp[i][j] = dp[i - 1][j - 1] + 1;
            else dp[i][j] = dp[i - 1][j] > dp[i][j - 1] ? dp[i - 1][j] : dp[i][j - 1];
        }
    return dp[n][m];
}
int main(void) { printf("%d %d %d\n", lcs("ABCBDAB", "BDCABA"), lcs("", "abc"), lcs("same", "same")); return 0; }'''),
    ('DP: 동전 개수(배열 크기 상수 #define)', r'''
#define MAXV 1000
int main(void) {
    int coins[] = {1, 5, 10, 25};
    int dp[MAXV + 1];
    dp[0] = 0;
    for (int v = 1; v <= MAXV; v++) {
        dp[v] = INT_MAX;
        for (int k = 0; k < 4; k++)
            if (coins[k] <= v && dp[v - coins[k]] + 1 < dp[v]) dp[v] = dp[v - coins[k]] + 1;
    }
    printf("%d %d %d\n", dp[63], dp[999], dp[MAXV]);
    return 0;
}'''),
    ('구조체 안의 구조체 배열·포인터 반환', r'''
typedef struct { char name[8]; int qty; } Item;
typedef struct { Item items[3]; int n; } Box;
Item *find(Box *b, const char *name) {
    for (int i = 0; i < b->n; i++) if (strcmp(b->items[i].name, name) == 0) return &b->items[i];
    return NULL;
}
int main(void) {
    Box b = {{{"pen", 3}, {"cup", 1}, {"map", 2}}, 3};
    Item *it = find(&b, "cup");
    it->qty += 10;
    printf("%d %d %d\n", b.items[1].qty, find(&b, "hat") == NULL, (int)(it - b.items));
    return 0;
}'''),
    ('qsort 구조체(길이순 → 사전순)', r'''
typedef struct { char w[12]; int len; } Word;
int cmp(const void *a, const void *b) {
    const Word *x = (const Word *)a, *y = (const Word *)b;
    if (x->len != y->len) return x->len - y->len;
    return strcmp(x->w, y->w);
}
int main(void) {
    const char *src[] = {"pear", "fig", "banana", "kiwi", "apple", "date"};
    Word ws[6];
    for (int i = 0; i < 6; i++) { strcpy(ws[i].w, src[i]); ws[i].len = strlen(src[i]); }
    qsort(ws, 6, sizeof(Word), cmp);
    for (int i = 0; i < 6; i++) printf("%s ", ws[i].w);
    printf("\n");
    return 0;
}'''),
    ('행렬 전치(제자리)·대각선 합', r'''
int main(void) {
    int m[4][4];
    for (int i = 0; i < 4; i++) for (int j = 0; j < 4; j++) m[i][j] = i * 4 + j;
    for (int i = 0; i < 4; i++) for (int j = i + 1; j < 4; j++) { int t = m[i][j]; m[i][j] = m[j][i]; m[j][i] = t; }
    int d1 = 0, d2 = 0;
    for (int i = 0; i < 4; i++) { d1 += m[i][i]; d2 += m[i][3 - i]; }
    printf("%d %d %d %d\n", m[0][1], m[3][0], d1, d2);
    return 0;
}'''),
    ('%% 와 실수 서식 섞기', r'''
int main(void) {
    double rate = 0.4567;
    printf("%5.2f%% [%8.3e] [%-12.4g] [%.0f]\n", rate * 100, 123456.0, 0.000012345, 1e15);
    return 0;
}'''),
    ('size_t 반복과 strlen', r'''
int main(void) {
    const char *s = "Mississippi";
    size_t n = strlen(s);
    int cnt = 0;
    for (size_t i = 0; i < n; i++) if (s[i] == 's') cnt++;
    size_t back = 0;
    for (size_t i = n; i > 0; i--) if (s[i - 1] == 'i') { back = i - 1; break; }
    printf("%zu %d %zu\n", n, cnt, back);
    return 0;
}'''),
    ('정수 나눗셈 결과를 실수에·평균 반올림', r'''
int main(void) {
    int sum = 17, n = 4;
    double a = sum / n, b = (double)sum / n, c = sum / (double)n;
    int r = (int)(b + 0.5);
    printf("%.2f %.2f %.2f %d %d\n", a, b, c, r, (sum * 10 / n + 5) / 10);
    return 0;
}'''),
    ('2차원 배열 행 정렬', r'''
int main(void) {
    int a[4][3] = {{3, 1, 2}, {1, 9, 9}, {3, 0, 0}, {1, 2, 3}};
    for (int i = 0; i < 4; i++)
        for (int j = 0; j < 3 - i && j < 3; j++) {
            int k = j + 1;
            if (k < 4 && (a[j][0] > a[k][0] || (a[j][0] == a[k][0] && a[j][1] > a[k][1])))
                for (int c = 0; c < 3; c++) { int t = a[j][c]; a[j][c] = a[k][c]; a[k][c] = t; }
        }
    for (int i = 0; i < 4; i++) printf("%d%d%d ", a[i][0], a[i][1], a[i][2]);
    printf("\n");
    return 0;
}'''),
    ('재귀: 거듭제곱·이진수·회문 재귀', r'''
long long power(long long b, int e) { if (e == 0) return 1; long long h = power(b, e / 2); return e % 2 ? h * h * b : h * h; }
void bin(int n) { if (n > 1) bin(n / 2); putchar('0' + n % 2); }
int pal(const char *s, int l, int r) { return l >= r ? 1 : (s[l] == s[r] && pal(s, l + 1, r - 1)); }
int main(void) {
    printf("%lld %lld ", power(3, 20), power(2, 62));
    bin(37);
    printf(" %d %d\n", pal("racecar", 0, 6), pal("abca", 0, 3));
    return 0;
}'''),
    ('문자 빈도로 애너그램', r'''
bool anagram(const char *a, const char *b) {
    int c[256] = {0};
    for (; *a; a++) c[(unsigned char)*a]++;
    for (; *b; b++) c[(unsigned char)*b]--;
    for (int i = 0; i < 256; i++) if (c[i]) return false;
    return true;
}
int main(void) { printf("%d %d %d\n", anagram("listen", "silent"), anagram("abc", "abd"), anagram("", "")); return 0; }'''),
    ('카이사르 암호(문자 회전)', r'''
void rot(char *s, int k) {
    for (; *s; s++) {
        if (*s >= 'a' && *s <= 'z') *s = 'a' + (*s - 'a' + k) % 26;
        else if (*s >= 'A' && *s <= 'Z') *s = 'A' + (*s - 'A' + k + 26) % 26;
    }
}
int main(void) {
    char s[] = "Hello, World! xyz";
    rot(s, 3);
    printf("%s\n", s);
    rot(s, 23);
    printf("%s\n", s);
    return 0;
}'''),
    ('구조체 값 전달은 복사', r'''
typedef struct { int v[3]; } Vec;
void bump(Vec x) { x.v[0] = 99; }
Vec bumped(Vec x) { x.v[0] += 1; return x; }
int main(void) {
    Vec a = {{1, 2, 3}};
    bump(a);
    Vec b = bumped(a);
    printf("%d %d %d\n", a.v[0], b.v[0], b.v[2]);
    return 0;
}'''),
    ('부동소수 비교·누적 오차', r'''
int main(void) {
    double s = 0;
    for (int i = 0; i < 10; i++) s += 0.1;
    printf("%d %d %.17g %.3f\n", s == 1.0, fabs(s - 1.0) < 1e-9, s, sqrt(-0.0));
    float f = 16777216.0f;
    f += 1.0f;
    printf("%.1f %d\n", f, (int)f);
    return 0;
}'''),
]


def gen_arith(seed):
    """정수 타입을 섞은 무작위 식(승격·일반 산술 변환·부호 없는 수·시프트·복합 대입·++/--)을 출력하는 프로그램."""
    import random
    R = random.Random(seed)
    types = [('char', -128, 127), ('signed char', -128, 127), ('unsigned char', 0, 255), ('short', -32768, 32767),
             ('unsigned short', 0, 65535), ('int', -2**31, 2**31 - 1), ('unsigned int', 0, 2**32 - 1), ('long', -2**63, 2**63 - 1),
             ('unsigned long', 0, 2**64 - 1), ('long long', -2**63, 2**63 - 1), ('unsigned long long', 0, 2**64 - 1), ('_Bool', 0, 1)]
    fmt = {'char': '%d', 'signed char': '%d', 'unsigned char': '%d', 'short': '%d', 'unsigned short': '%d', 'int': '%d', 'unsigned int': '%u',
           'long': '%ld', 'unsigned long': '%lu', 'long long': '%lld', 'unsigned long long': '%llu', '_Bool': '%d'}
    out = []
    for i, (ty, lo, hi) in enumerate(types):
        c = R.random()
        v = R.choice([lo, hi, 0, 1, lo + 1, hi - 1]) if c < 0.3 else (R.randint(max(lo, -300), min(hi, 300)) if c < 0.6 else R.randint(lo, hi))
        lit = f'{v}ULL' if v > 2**63 - 1 else ('(-9223372036854775807LL-1)' if v == -2**63 else f'{v}LL')
        out.append(f'    {ty} v{i} = ({ty})({lit});')
    casts = ['int', 'unsigned int', 'long long', 'unsigned long long', 'char', 'unsigned char', 'short', 'double', '_Bool']
    for k in range(200):
        a, b = R.randrange(12), R.randrange(12)
        op = R.choice(['+', '-', '*', '/', '%', '&', '|', '^', '<<', '>>', '<', '>', '==', '!=', '<=', '>=', '&&', '||'])
        cs = casts if op not in ('%', '&', '|', '^', '<<', '>>') else casts[:-2] + ['_Bool']
        ea = f'({R.choice(cs)})v{a}' if R.random() < 0.3 else f'v{a}'
        eb = f'{R.randint(-5, 40)}' if R.random() < 0.2 else f'v{b}'
        if op in ('/', '%'):
            eb = f'((({eb}) == 0 || ({eb}) == -1) ? 3 : ({eb}))'
        if op in ('<<', '>>'):
            eb = f'(({eb}) & 7)'
            if op == '<<':
                ea = f'((unsigned long long){ea})'
        tt = R.choice(['long long', 'unsigned long long', 'int', 'unsigned int', 'char', 'double'])
        f = {'long long': '%lld', 'unsigned long long': '%llu', 'int': '%d', 'unsigned int': '%u', 'char': '%d', 'double': '%.3f'}[tt]
        out.append(f'    printf("%d:{f}\\n", {k}, ({tt})({ea} {op} {eb}));')
    for k in range(40):
        a, b = R.randrange(11), R.randrange(11)
        op = R.choice(['+=', '-=', '*=', '&=', '|=', '^=', '<<=', '>>='])
        rhs = f'v{b}' if op not in ('<<=', '>>=') else f'(v{b} & 3)'
        out.append(f'    {{ {types[a][0]} t = v{a}; t {op} {rhs}; printf("c{k}:{fmt[types[a][0]]}\\n", t); }}')
    for k in range(20):
        a = R.randrange(11)
        op = R.choice(['++', '--'])
        e = f'{op}t' if R.random() < 0.5 else f't{op}'
        f = fmt[types[a][0]]
        out.append(f'    {{ {types[a][0]} t = v{a}; {types[a][0]} r = {e}; printf("i{k}:{f} {f}\\n", t, r); }}')
    return 'int main(void) {\n' + '\n'.join(out) + '\n    return 0;\n}\n'


def gen_fmt(seed):
    """무작위 printf 서식(플래그·폭·정밀도·길이)을 glibc와 비교하는 프로그램. (%#g 반올림 자리 올림은 glibc 특이 동작이라 뺀다)"""
    import random
    R = random.Random(seed)
    ints = [0, 1, -1, 7, -7, 42, 255, 256, 65535, 2147483647, -2147483648, 1000000, -99999, 12345]
    dbls = ['0.0', '-0.0', '1.0', '-1.5', '0.5', '2.5', '3.14159265358979', '1e-5', '123456.789', '1e20', '-2.5e-7', '99.995',
            '0.125', '1.0/0.0', '-1.0/0.0', '0.1', '1e300', '5e-324', '100.0', '0.000123456']
    strs = ['""', '"a"', '"hello"', '"hello world"', '"가나"']
    out = []
    for k in range(300):
        flags = ''.join(R.sample('-+ #0', R.randint(0, 2)))
        width = R.choice(['', '', str(R.randint(1, 12))])
        prec = R.choice(['', '', '', '.' + str(R.randint(0, 8)), '.'])
        c = R.random()
        if c < 0.35:
            conv = R.choice('diuxXo')
            ln = R.choice(['', '', 'l', 'll', 'h', 'hh'])
            ct = {'': 'int', 'l': 'long', 'll': 'long long', 'h': 'int', 'hh': 'int'}[ln]
            arg = f'({"unsigned " if conv in "uxXo" else ""}{ct})({R.choice(ints)}LL)'
            spec = f'%{flags}{width}{prec}{ln}{conv}'
        elif c < 0.75:
            conv = R.choice('feEgGF')
            if conv in 'gG':
                flags = flags.replace('#', '')
            spec = f'%{flags}{width}{prec}{R.choice(["", "l"])}{conv}'
            arg = R.choice(dbls)
        elif c < 0.9:
            spec = f'%{flags.replace("0", "").replace("#", "").replace("+", "").replace(" ", "")}{width}{prec}s'
            arg = R.choice(strs)
        else:
            spec = f'%{flags.replace("0", "").replace("#", "").replace("+", "").replace(" ", "")}{width}c'
            arg = str(R.choice([65, 97, 48, 32, 126]))
        out.append(f'    printf("{k}:[{spec}]\\n", {arg});')
    return 'int main(void) {\n' + '\n'.join(out) + '\n    return 0;\n}\n'


PROGRAMS += [(f'무작위 정수 식(seed {s})', gen_arith(s)) for s in (1, 2, 3)]
PROGRAMS += [(f'무작위 printf 서식(seed {s})', gen_fmt(s)) for s in (1, 2)]

# ---------------------------------------------------------------- 2. run_cases_c 채점(+ gcc 대조)
GRADE = [
    ('배열 인자 + 길이(derived)', r'''
int solution(int arr[], int arr_len) {
    int s = 0;
    for (int i = 0; i < arr_len; i++) if (arr[i] % 2 == 0) s += arr[i];
    return s;
}''', {'derived': {'arr_len': 'len(arr)'}}, [([[1, 2, 3, 4, 10]], 16), ([[7]], 0), ([[]], 0), ([[-2, -4, 5]], -6)]),
    ('배열 인자 + 길이(args에 직접)', r'''
int solution(int arr[], int n, int k) {
    int c = 0;
    for (int i = 0; i < n; i++) if (arr[i] > k) c++;
    return c;
}''', {}, [([[5, 1, 9, 3], 4, 3], 2), ([[1, 1], 2, 1], 0)]),
    ('문자열 인자', r'''
int solution(char* s) {
    int v = 0;
    for (int i = 0; s[i] != '\0'; i++) {
        char c = s[i];
        if (c == 'a' || c == 'e' || c == 'i' || c == 'o' || c == 'u') v++;
    }
    return v;
}''', {}, [(['programming'], 3), ([''], 0), (['aeiou xyz'], 5)]),
    ('문자열 끝 s[N] 읽기(널 문자)', r'''
#include <string.h>
int solution(const char* s) {
    int n = strlen(s);
    return s[n] == '\0' ? n : -1;
}''', {}, [(['abc'], 3), ([''], 0)]),
    ('2차원 배열 int b[][4]', r'''
int solution(int board[][4], int board_len) {
    int best = 0;
    for (int i = 0; i < board_len; i++) {
        int s = 0;
        for (int j = 0; j < 4; j++) s += board[i][j];
        if (s > best) best = s;
    }
    return best;
}''', {'derived': {'board_len': 'len(board)'}}, [([[[1, 2, 3, 4], [9, 9, 9, 9], [0, 0, 0, 1]]], 36), ([[[0, 0, 0, 0]]], 0)]),
    ('int points[][2]', r'''
int solution(int points[][2], int points_len) {
    int far = 0;
    for (int i = 0; i < points_len; i++) {
        int d = points[i][0] * points[i][0] + points[i][1] * points[i][1];
        if (d > far) far = d;
    }
    return far;
}''', {'derived': {'points_len': 'len(points)'}}, [([[[1, 2], [3, 4], [-5, 0]]], 25)]),
    ('int** + 행·열 길이(derived)', r'''
int solution(int** g, int rows, int cols) {
    int s = 0;
    for (int i = 0; i < rows; i++) for (int j = 0; j < cols; j++) if (i == j) s += g[i][j];
    return s * 100 + rows * 10 + cols;
}''', {'derived': {'rows': 'len(g)', 'cols': 'len(g[0])'}}, [([[[1, 2, 3], [4, 5, 6]]], 623), ([[[7]]], 711)]),
    ('문자열 배열 char* words[]', r'''
#include <string.h>
int solution(char* words[], int words_len) {
    int total = 0;
    for (int i = 0; i < words_len; i++) total += strlen(words[i]);
    return total;
}''', {'derived': {'words_len': 'len(words)'}}, [([['apple', 'kiwi', '']], 9), ([['한글']], 6)]),
    ('const int customer[]', r'''
int solution(const int customer[], int customer_len, int limit) {
    int served = 0, used = 0;
    for (int i = 0; i < customer_len; i++) {
        if (used + customer[i] > limit) break;
        used += customer[i];
        served++;
    }
    return served;
}''', {'derived': {'customer_len': 'len(customer)'}}, [([[3, 4, 5, 1], 8], 2), ([[9], 8], 0)]),
    ('int* 반환 + spec.ret.len', r'''
#include <stdlib.h>
int* solution(int arr[], int arr_len) {
    int* r = (int*)malloc(sizeof(int) * arr_len);
    for (int i = 0; i < arr_len; i++) r[i] = arr[arr_len - 1 - i] * 2;
    return r;
}''', {'derived': {'arr_len': 'len(arr)'}, 'ret': {'len': 'arr_len'}}, [([[1, 2, 3]], [6, 4, 2]), ([[5]], [10])]),
    ('int* 반환 + 길이 식(n*2)', r'''
#include <stdlib.h>
int* solution(int n) {
    int* r = malloc(sizeof(int) * n * 2);
    for (int i = 0; i < n * 2; i++) r[i] = i % n;
    return r;
}''', {'ret': {'len': 'n*2'}}, [([3], [0, 1, 2, 0, 1, 2])]),
    ('char* 반환(대문자 복사)', r'''
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
char* solution(char* s) {
    int n = strlen(s);
    char* r = malloc(n + 1);
    for (int i = 0; i < n; i++) r[i] = toupper(s[i]);
    r[n] = '\0';
    return r;
}''', {}, [(['hello World'], 'HELLO WORLD'), ([''], '')]),
    ('sprintf로 숫자를 문자열로', r'''
#include <stdio.h>
#include <stdlib.h>
char* solution(int a, int b) {
    char* buf = malloc(32);
    sprintf(buf, "%d:%02d", a, b);
    return buf;
}''', {}, [([12, 5], '12:05'), ([-3, 0], '-3:00')]),
    ('bool 반환', r'''
#include <stdbool.h>
bool solution(int n) {
    if (n < 2) return false;
    for (int i = 2; i * i <= n; i++) if (n % i == 0) return false;
    return true;
}''', {}, [([2], True), ([15], False), ([97], True), ([1], False)]),
    ('double 반환(평균)', r'''
double solution(int arr[], int n) {
    int s = 0;
    for (int i = 0; i < n; i++) s += arr[i];
    return (double)s / n;
}''', {}, [([[1, 2, 4], 3], 7 / 3), ([[5], 1], 5.0)]),
    ('long long N(최대 5×10^11)', r'''
long long solution(long long N) {
    long long a = N % 1000000007, b = (N + 1) % 1000000007;
    return a * b % 1000000007 + N / 3;
}''', {}, [([500000000000], (500000000000 % 1000000007) * (500000000001 % 1000000007) % 1000000007 + 500000000000 // 3), ([1], 2)]),
    ('char 반환(가장 많은 글자)', r'''
char solution(char* s) {
    int cnt[26] = {0};
    char best = 'a';
    for (int i = 0; s[i]; i++) cnt[s[i] - 'a']++;
    for (int c = 0; c < 26; c++) if (cnt[c] > cnt[best - 'a']) best = 'a' + c;
    return best;
}''', {}, [(['banana'], 'a'), (['zzy'], 'z')]),
    ('char** 반환(문자열 목록)', r'''
#include <stdlib.h>
#include <string.h>
char** solution(char* words[], int n) {
    char** r = malloc(sizeof(char*) * n);
    for (int i = 0; i < n; i++) {
        r[i] = malloc(strlen(words[i]) + 2);
        strcpy(r[i], words[i]);
        strcat(r[i], "!");
    }
    return r;
}''', {'ret': {'len': 'n'}}, [([['hi', 'yo'], 2], ['hi!', 'yo!'])]),
    ('int** 반환(len·len2)', r'''
#include <stdlib.h>
int** solution(int n) {
    int** g = malloc(sizeof(int*) * n);
    for (int i = 0; i < n; i++) {
        g[i] = malloc(sizeof(int) * n);
        for (int j = 0; j < n; j++) g[i][j] = i * n + j;
    }
    return g;
}''', {'ret': {'len': 'n', 'len2': 'n'}}, [([2], [[0, 1], [2, 3]])]),
    ('VLA int fibo[N + 1]', r'''
int solution(int N) {
    int fibo[N + 1];
    fibo[0] = 0;
    if (N > 0) fibo[1] = 1;
    for (int i = 2; i <= N; i++) fibo[i] = (fibo[i - 1] + fibo[i - 2]) % 1000;
    return fibo[N];
}''', {}, [([10], 55), ([0], 0), ([30], 832040 % 1000)]),
    ('INT_MIN 최댓값', r'''
#include <limits.h>
int solution(int cards[], int cards_len) {
    int best = INT_MIN;
    for (int i = 0; i < cards_len; i++) for (int j = i + 1; j < cards_len; j++) if (cards[i] * cards[j] > best) best = cards[i] * cards[j];
    return best;
}''', {'derived': {'cards_len': 'len(cards)'}}, [([[-7, -3, 2, 4]], 21), ([[-1, 5]], -5)]),
    ('구조체 배열 인자(dict 목록)', r'''
typedef struct { int x; int y; } Point;
int solution(Point* pts, int n) {
    int s = 0;
    for (int i = 0; i < n; i++) s += pts[i].x * pts[i].y;
    return s;
}''', {'derived': {'n': 'len(pts)'}}, [([[{'x': 1, 'y': 2}, {'x': 3, 'y': 4}]], 14)]),
    ('printf 출력은 stdout으로', r'''
#include <stdio.h>
int solution(int a) {
    printf("a=%d\n", a);
    return a + 1;
}''', {}, [([1], 2), ([2], 3)]),
]

# ---------------------------------------------------------------- 3. 오류 메시지
RUNTIME_ERRORS = [
    ('범위 밖 읽기', r'''
int solution(int arr[], int n) {
    int s = 0;
    for (int i = 0; i <= n; i++) s += arr[i];
    return s;
}''', [[1, 2, 3, 4, 5], 5], '배열(메모리) 범위를 벗어났어요: arr[5] (크기 5)', 4),
    ('지역 배열 범위 밖 쓰기', r'''
int solution(int n) {
    int a[3];
    for (int i = 0; i < n; i++) a[i] = i;
    return a[0];
}''', [4], '배열(메모리) 범위를 벗어났어요: a[3] (크기 3)', 4),
    ('음수 인덱스', r'''
int solution(int n) {
    int b[2][3] = {{0}};
    return b[n][0];
}''', [-1], '배열(메모리) 범위를 벗어났어요: b[-1][0] (크기 2×3)', 4),
    ('초기화하지 않은 변수', r'''
int solution(int arr[], int n) {
    int answer;
    for (int i = 0; i < n; i++) answer += arr[i];
    return answer;
}''', [[1, 2], 2], '초기화하지 않은 값을 읽었어요: answer', 4),
    ('초기화하지 않은 배열 칸', r'''
int solution(int n) {
    int a[5];
    a[0] = 1;
    return a[0] + a[n];
}''', [2], '초기화하지 않은 값을 읽었어요: a[2]', 5),
    ('초기화하지 않은 malloc 영역', r'''
#include <stdlib.h>
int solution(int n) {
    int *p = malloc(sizeof(int) * n);
    p[0] = 5;
    return p[1];
}''', [3], '초기화하지 않은 값을 읽었어요: malloc 메모리[1]', 6),
    ('초기화하지 않은 구조체 멤버', r'''
struct S { int a; int b; };
int solution(int n) {
    struct S s;
    s.a = n;
    return s.a + s.b;
}''', [3], '초기화하지 않은 값을 읽었어요: s.b', 6),
    ('NULL 역참조', r'''
#include <stddef.h>
int solution(int n) {
    int *p = NULL;
    return *p + n;
}''', [1], 'NULL 포인터를 사용했어요', 5),
    ('NULL 구조체 포인터', r'''
#include <stdlib.h>
typedef struct Node { int v; struct Node* next; } Node;
int solution(int n) {
    Node* h = malloc(sizeof(Node));
    h->v = n;
    h->next = NULL;
    return h->next->v;
}''', [1], 'NULL 포인터를 사용했어요', 8),
    ('0으로 나누기', r'''
int solution(int a, int b) { return a / b; }''', [3, 0], '0으로 나눴어요', 2),
    ('나머지 0', r'''
int solution(int a, int b) { return a % b; }''', [3, 0], '0으로 나눈 나머지', 2),
    ('무한 반복 → 시간 초과', r'''
int solution(int n) {
    int i = 0;
    while (i < n) { n++; i++; }
    return i;
}''', [1], '시간 초과', None),
    ('깊은 재귀', r'''
int f(int n) { return f(n + 1) + 1; }
int solution(int n) { return f(n); }''', [0], '재귀가 너무 깊어요', None),
    ('return 없이 끝남', r'''
int solution(int n) {
    if (n > 0) return 1;
}''', [-1], 'solution 함수가 값을 return 하지 않고 끝났어요', 2),
    ('지역 배열 주소 반환', r'''
int* solution(int n) {
    int a[3] = {1, 2, 3};
    return a;
}''', [3], '이미 해제(free)했거나 함수가 끝나 사라진 메모리', None),
    ('문자열 상수 바꾸기', r'''
char* solution(int n) {
    char* s = "hello";
    s[0] = 'H';
    return s;
}''', [1], '문자열 상수는 바꿀 수 없어요', 4),
    ('free 두 번', r'''
#include <stdlib.h>
int solution(int n) {
    int* p = malloc(4);
    free(p);
    free(p);
    return n;
}''', [1], '이미 해제(free)한 메모리를 또 free 했어요', 6),
    ('해제한 메모리 읽기', r'''
#include <stdlib.h>
int solution(int n) {
    int* p = malloc(sizeof(int));
    *p = n;
    free(p);
    return *p;
}''', [1], '이미 해제(free)했거나', 7),
    ('널 문자 없는 문자열', r'''
#include <string.h>
int solution(int n) {
    char s[3] = {'a', 'b', 'c'};
    return strlen(s) + n;
}''', [0], "문자열 끝('\\0')을 찾지 못하고", 5),
    ('strcpy 공간 부족', r'''
#include <string.h>
int solution(int n) {
    char s[4];
    strcpy(s, "hello");
    return n;
}''', [0], '배열(메모리) 범위를 벗어났어요: s[4] (크기 4)', 5),
    ('printf %d에 실수', r'''
#include <stdio.h>
int solution(int n) {
    printf("%d\n", n * 1.5);
    return n;
}''', [2], 'printf의 %d에는 정수를 넣어야 하는데 실수(double) 값을 넣었어요', 4),
    ('exit 호출', r'''
#include <stdlib.h>
int solution(int n) { exit(1); return n; }''', [2], 'exit(1)가 호출되어', None),
]

COMPILE_ERRORS = [
    ('세미콜론 빠짐', 'int solution(int n) {\n    int a = n\n    return a;\n}', '문법 오류(3번째 줄)', 3),
    ('닫는 중괄호 빠짐', 'int solution(int n) {\n    return n;\n', '코드가 중간에 끝났어요', None),
    ('선언하지 않은 이름', 'int solution(int n) {\n    return n + count;\n}', '선언하지 않은 이름이에요: count', 2),
    ('지원하지 않는 함수', '#include <stdio.h>\nint solution(int n) {\n    int x;\n    scanf("%d", &x);\n    return x;\n}', '입력 함수(scanf)는 쓰지 않아요', 4),
    ('철자 틀린 함수', 'int solution(int n) {\n    return sqr(n);\n}', '지원하지 않는 함수: sqr', 2),
    ('인자 수 불일치', 'int add(int a, int b) { return a + b; }\nint solution(int n) {\n    return add(n, 1, 2);\n}', '인자 수가 맞지 않아요: add 함수는 인자 2개가 필요한데 3개', 3),
    ('포인터에 정수 대입', 'int solution(int n) {\n    int *p;\n    p = n;\n    return 0;\n}', '대입 타입이 맞지 않아요: 포인터(int*)에 int 값을 넣을 수 없어요', 3),
    ('정수에 포인터 대입', 'int solution(int arr[], int n) {\n    int x = arr;\n    return x;\n}', '초기화 타입이 맞지 않아요: int에 int* 값을 넣을 수 없어요', 2),
    ('배열에 대입', 'int solution(int n) {\n    int a[3], b[3] = {0};\n    a = b;\n    return 0;\n}', '배열 전체에는 = 로 값을 넣을 수 없어요', 3),
    ('지원하지 않는 헤더', '#include <conio.h>\nint solution(int n) { return n; }', '지원하지 않는 헤더예요: <conio.h>', 1),
    ('함수형 매크로', '#define SQ(x) ((x)*(x))\nint solution(int n) { return SQ(n); }', '함수형 매크로', 1),
    ('break 위치', 'int solution(int n) {\n    break;\n    return n;\n}', '반복문이나 switch 밖에서 break', 2),
    ('const 바꾸기', 'int solution(const int arr[], int n) {\n    arr[0] = n;\n    return 0;\n}', 'const로 정한 값은 바꿀 수 없어요', 2),
    ('-> 와 . 혼동', 'struct P { int x; };\nint solution(int n) {\n    struct P p = {n};\n    return p->x;\n}', '구조체 변수에는 -> 대신 . 을 써요', 4),
    ('실수 나머지', 'int solution(int n) {\n    double d = n % 2.0;\n    return 0;\n}', '실수에는 % 연산을 쓸 수 없어요', 2),
    ('쓸 수 없는 문자', 'int solution(int n) {\n    return n；\n}', '문법 오류', 2),
]


# ---------------------------------------------------------------- 실행 도구
def gcc_run(code, d, tag):
    src = os.path.join(d, f'{tag}.c')
    exe = os.path.join(d, tag)
    with open(src, 'w', encoding='utf-8') as f:
        f.write(code)
    p = subprocess.run(['gcc', *GCC_FLAGS, src, '-o', exe, '-lm'], capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        return {'compile': p.stderr[-600:]}
    r = subprocess.run([exe], capture_output=True, timeout=20, env=ENV)
    return {'stdout': r.stdout.decode('utf-8', 'replace'), 'exit': r.returncode & 0xFF, 'stderr': r.stderr.decode('utf-8', 'replace')}


class T:
    def __init__(self, verbose):
        self.n = 0
        self.fail = []
        self.verbose = verbose

    def ok(self, name, cond, detail=''):
        self.n += 1
        if not cond:
            self.fail.append(f'{name}: {detail}')
            print(f'  ✗ {name}: {detail}'[:1500])
        elif self.verbose:
            print(f'  ✓ {name}')


def main():
    args = sys.argv[1:]
    verbose = '-v' in args
    filt = args[args.index('-k') + 1] if '-k' in args else None
    if shutil.which('gcc') is None:
        print('gcc가 없어요. gcc를 설치한 뒤 실행해 주세요.')
        return 1
    t = T(verbose)
    sel = (lambda name: filt is None or filt in name)

    # 1. 프로그램 출력 비교
    progs = [(i, n, H + c) for i, (n, c) in enumerate(PROGRAMS) if sel(n)]
    print(f'1) gcc와 출력 비교: 프로그램 {len(progs)}개')
    d = tempfile.mkdtemp(prefix='saicerti-tci-')
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(2, os.cpu_count() or 2)) as ex:
            futs = {i: ex.submit(gcc_run, c, d, f'p{i}') for i, _, c in progs}
            for i, name, code in progs:
                t0 = time.time()
                mine = cinterp.run_program(code)
                dt = time.time() - t0
                ref = futs[i].result()
                if 'compile' in ref:
                    t.ok(name, False, 'gcc 컴파일 실패: ' + ref['compile'])
                    continue
                if mine['error']:
                    t.ok(name, False, f'인터프리터 오류: {mine["error"]}')
                    continue
                same = mine['stdout'] == ref['stdout'] and mine['exit'] == ref['exit']
                t.ok(name, same, f'출력이 달라요\n    gcc : {ref["stdout"]!r} (종료 {ref["exit"]})\n    해석: {mine["stdout"]!r} (종료 {mine["exit"]})')
                if verbose:
                    print(f'      {dt * 1000:.0f}ms')
    finally:
        shutil.rmtree(d, ignore_errors=True)

    # 2. 채점 연결
    grades = [g for g in GRADE if sel(g[0])]
    print(f'2) run_cases_c 채점 + gcc 대조: {len(grades)}묶음')
    for name, code, spec, cases in grades:
        cs = [{'args': a, 'expected': e} for a, e in cases]
        out = json.loads(harness.run_cases_c(code, 'solution', json.dumps(cs), 'exact', json.dumps(spec)))
        if out['compile']:
            t.ok(name, False, f'컴파일 오류: {out["compile"]}')
            continue
        t.ok(name + ' (기댓값)', all(r['ok'] for r in out['results']), json.dumps(out['results'], ensure_ascii=False))
        g = cref.run_gcc(code, 'solution', cs, spec)
        good = all(x.get('ok') and harness.same(x['value'], c['expected']) for x, c in zip(g, cs))
        t.ok(name + ' (gcc 대조)', good, json.dumps(g, ensure_ascii=False))
        if name.startswith('printf 출력'):
            t.ok(name + ' (stdout)', out['stdout'] == 'a=1\na=2\n' and all(x.get('stdout') == f'a={i + 1}\n' for i, x in enumerate(g)), repr(out['stdout']))
    # 테스트마다 전역 상태 되돌림
    code = 'int calls = 0;\nint solution(int n) { static int k = 10; calls++; k++; return calls * 100 + k; }'
    out = json.loads(harness.run_cases_c(code, 'solution', json.dumps([{'args': [1], 'expected': 111}, {'args': [2], 'expected': 111}]), 'exact', '{}'))
    t.ok('테스트마다 전역·static 초기화', all(r['ok'] for r in out['results']), json.dumps(out, ensure_ascii=False))
    out = json.loads(harness.run_cases_c('int main(void) { return 0; }', 'solution', '[]', 'exact', '{}'))
    t.ok('solution 함수 없음', out['compile'] and 'solution 함수가 없어요' in out['compile']['message'], json.dumps(out, ensure_ascii=False))
    out = json.loads(harness.run_cases_c('int solution(int a) { return a; }\nint main(void) { return solution(1) / 0; }', 'solution', json.dumps([{'args': [4], 'expected': 4}]), 'exact', '{}'))
    t.ok('main은 부르지 않음', out['results'] and out['results'][0]['ok'], json.dumps(out, ensure_ascii=False))
    out = json.loads(harness.run_cases_c('int solution(int a) { return a; }', 'solution', json.dumps([{'args': [1, 2], 'expected': 1}]), 'exact', '{}'))
    t.ok('인자 수 오류는 결과 오류로', not out['results'][0]['ok'] and out['results'][0]['error']['type'] == 'ArgError', json.dumps(out, ensure_ascii=False))

    # 3. 오류 메시지
    rts = [r for r in RUNTIME_ERRORS if sel(r[0])]
    print(f'3) 런타임 오류 {len(rts)}개 · 컴파일 오류 {len(COMPILE_ERRORS)}개')
    for name, code, args, want, line in rts:
        p = cinterp.compile_c(code)
        if '시간 초과' in want:
            p.max_steps = 300000
        try:
            got = p.call('solution', args, {'ret': {'len': 3}})
            t.ok(name, False, f'오류가 나야 하는데 {got!r}')
        except cinterp.CError as e:
            t.ok(name, want in e.msg and (line is None or e.line == line), f'{e.msg!r} (줄 {e.line}) — 기대: {want!r} 줄 {line}')
    for name, code, want, line in COMPILE_ERRORS:
        if not sel(name):
            continue
        try:
            cinterp.compile_c(code)
            t.ok(name, False, '컴파일 오류가 나야 해요')
        except cinterp.CError as e:
            t.ok(name, want in e.msg and (line is None or e.line == line), f'{e.msg!r} (줄 {e.line}) — 기대: {want!r} 줄 {line}')
    # 시간 초과는 기본 단계 제한으로도 멈춘다(while(1))
    if sel('시간 초과 기본'):
        t0 = time.time()
        r = cinterp.run_program('int main(void) { int x = 0; while (1) { x++; } return x; }')
        dt = time.time() - t0
        t.ok('시간 초과 기본 제한(2,000만 단계)', r['error'] is not None and r['error']['type'] == 'TimeoutError', f'{r} {dt:.1f}s')
        print(f'   무한 반복이 기본 제한(2,000만 단계)으로 멈추기까지 {dt:.1f}초')

    # 4. derived · ret.len
    print('4) expand_args · eval_len')
    ex = cinterp.expand_args
    t.ok('derived len', ex(['arr', 'arr_len'], [[1, 2, 3]], {'derived': {'arr_len': 'len(arr)'}}) == [[1, 2, 3], 3])
    t.ok('derived 앞쪽 매개변수', ex(['n', 'arr', 'k'], [[4, 5], 9], {'derived': {'n': 'len(arr)'}}) == [2, [4, 5], 9])
    t.ok('derived len(x[0])·상수', ex(['b', 'r', 'c', 'z'], [[[1, 2, 3], [4, 5, 6]]], {'derived': {'r': 'len(b)', 'c': 'len(b[0])', 'z': '7'}}) == [[[1, 2, 3], [4, 5, 6]], 2, 3, 7])
    t.ok('derived 문자열 길이(바이트)', ex(['s', 'n'], ['가a'], {'derived': {'n': 'len(s)'}}) == ['가a', 4])
    for bad, why in ((['arr', 'n'], '인자 수'), ):
        try:
            ex(bad, [[1], 1], {'derived': {'n': 'len(arr)'}})
            t.ok('derived 인자 수 오류', False, '오류가 나야 해요')
        except ValueError as e:
            t.ok('derived 인자 수 오류', why in str(e), str(e))
    try:
        ex(['arr', 'n'], [[1]], {'derived': {'n': 'len(arr)*2'}})
        t.ok('derived 허용 식만', False, '오류가 나야 해요')
    except ValueError as e:
        t.ok('derived 허용 식만', 'len(이름)' in str(e), str(e))
    ev = cinterp.eval_len
    env = {'n': 4, 'arr': [1, 2, 3], 'g': [[1, 2]]}
    t.ok('ret.len 식', [ev(5, env), ev('n', env), ev('n*2', env), ev('n+1', env), ev('len(arr)', env), ev('len(g[0])', env), ev('(n-1)*len(arr)', env)] == [5, 4, 8, 5, 3, 2, 9])

    # 5. 성능
    print('5) 성능')
    perf = []
    for nm, body, want in (
        ('int 합 100만 번', 'int s = 0; for (int i = 0; i < 1000000; i++) s += i; printf("%d\\n", s);', '1783293664\n'),
        ('long long 합 100만 번', 'long long s = 0; for (int i = 0; i < 1000000; i++) s += i; printf("%lld\\n", s);', '499999500000\n'),
        ('배열 읽기·쓰기 100만 번', 'int a[1000] = {0}; long long s = 0; for (int i = 0; i < 1000000; i++) { a[i % 1000] += i & 7; s += a[(i * 7) % 1000]; } printf("%lld\\n", s);', None),
        ('함수 호출 fib(25)', None, None),
    ):
        code = '#include <stdio.h>\n' + ('int fib(int n) { return n < 2 ? n : fib(n - 1) + fib(n - 2); }\nint main(void) { printf("%d\\n", fib(25)); return 0; }' if body is None else f'int main(void) {{ {body} return 0; }}')
        t0 = time.time()
        r = cinterp.run_program(code)
        dt = time.time() - t0
        perf.append((nm, dt))
        print(f'   {nm}: {dt:.2f}초')
        if want is not None:
            t.ok(nm + ' 결과', r['stdout'] == want, repr(r))
    t.ok('성능 목표(100만 번 반복 ≤ 2초)', perf[0][1] <= 2.0, f'{perf[0][1]:.2f}초')

    print()
    if t.fail:
        print(f'✗ {t.n}개 중 {len(t.fail)}개 실패')
        return 1
    print(f'✓ {t.n}개 모두 통과')
    return 0


if __name__ == '__main__':
    sys.exit(main())
