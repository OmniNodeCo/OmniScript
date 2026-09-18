/* SHA-256, from the FIPS 180-4 recipe. Small and dependency-free. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* Public domain style constants: the fractional parts of the cube roots of
 * the first 64 primes.
 */
static const uint32_t K[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
    0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
    0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
    0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
    0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
    0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
};

typedef struct {
    uint32_t h[8];
    uint64_t len;
    unsigned char buf[64];
    size_t buflen;
} Sha256;

static uint32_t rotr(uint32_t x, int n) {
    return (x >> n) | (x << (32 - n));
}

static void block(Sha256 *s, const unsigned char *p) {
    uint32_t w[64], a, b, c, d, e, f, g, h, t1, t2;
    int i;
    for (i = 0; i < 16; i++)
        w[i] = ((uint32_t)p[i * 4] << 24) | ((uint32_t)p[i * 4 + 1] << 16) |
               ((uint32_t)p[i * 4 + 2] << 8) | (uint32_t)p[i * 4 + 3];
    for (i = 16; i < 64; i++) {
        uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
        uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    a = s->h[0];
    b = s->h[1];
    c = s->h[2];
    d = s->h[3];
    e = s->h[4];
    f = s->h[5];
    g = s->h[6];
    h = s->h[7];
    for (i = 0; i < 64; i++) {
        uint32_t s1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
        uint32_t ch = (e & f) ^ (~e & g);
        t1 = h + s1 + ch + K[i] + w[i];
        {
            uint32_t s0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
            uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
            t2 = s0 + maj;
        }
        h = g;
        g = f;
        f = e;
        e = d + t1;
        d = c;
        c = b;
        b = a;
        a = t1 + t2;
    }
    s->h[0] += a;
    s->h[1] += b;
    s->h[2] += c;
    s->h[3] += d;
    s->h[4] += e;
    s->h[5] += f;
    s->h[6] += g;
    s->h[7] += h;
}

static void sha256_init(Sha256 *s) {
    s->h[0] = 0x6a09e667;
    s->h[1] = 0xbb67ae85;
    s->h[2] = 0x3c6ef372;
    s->h[3] = 0xa54ff53a;
    s->h[4] = 0x510e527f;
    s->h[5] = 0x9b05688c;
    s->h[6] = 0x1f83d9ab;
    s->h[7] = 0x5be0cd19;
    s->len = 0;
    s->buflen = 0;
}

static void sha256_feed(Sha256 *s, const unsigned char *data, size_t n) {
    s->len += (uint64_t)n;
    while (n) {
        size_t take = 64 - s->buflen;
        if (take > n)
            take = n;
        memcpy(s->buf + s->buflen, data, take);
        s->buflen += take;
        data += take;
        n -= take;
        if (s->buflen == 64) {
            block(s, s->buf);
            s->buflen = 0;
        }
    }
}

static void sha256_hex(Sha256 *s, char out[65]) {
    unsigned char pad[128];
    uint64_t bits = s->len * 8;
    size_t need = s->buflen < 56 ? 56 - s->buflen : 120 - s->buflen;
    int i;
    memset(pad, 0, sizeof(pad));
    pad[0] = 0x80;
    sha256_feed(s, pad, need);
    for (i = 0; i < 8; i++)
        pad[i] = (unsigned char)(bits >> (56 - i * 8));
    sha256_feed(s, pad, 8);
    for (i = 0; i < 8; i++)
        sprintf(out + i * 8, "%08x", s->h[i]);
    out[64] = '\0';
}

/* Hex digest of a file, or -1 when it cannot be read. */
int sha256_file(const char *path, char out[65]);

int sha256_file(const char *path, char out[65]) {
    FILE *f = fopen(path, "rb");
    Sha256 s;
    unsigned char buf[8192];
    size_t n;
    if (!f)
        return -1;
    sha256_init(&s);
    while ((n = fread(buf, 1, sizeof(buf), f)) > 0)
        sha256_feed(&s, buf, n);
    if (ferror(f)) {
        fclose(f);
        return -1;
    }
    fclose(f);
    sha256_hex(&s, out);
    return 0;
}
