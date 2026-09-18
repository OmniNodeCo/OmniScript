/* The lexer: source text to tokens. */
#include "omni.h"

#include <ctype.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    Token *toks;
    int len, cap;
    Arena *a;
} Lexer;

static void emit(Lexer *lx, TokKind kind, char *text, double num,
                 int line, int col) {
    Token *t;
    if (lx->len == lx->cap) {
        int ncap = lx->cap ? lx->cap * 2 : 64;
        Token *nt = arena_alloc(lx->a, sizeof(Token) * (size_t)ncap);
        if (lx->toks)
            memcpy(nt, lx->toks, sizeof(Token) * (size_t)lx->len);
        lx->toks = nt;
        lx->cap = ncap;
    }
    t = &lx->toks[lx->len++];
    t->kind = kind;
    t->text = text;
    t->num = num;
    t->line = line;
    t->col = col;
}

static int is_name_start(char c) {
    return c == '_' || (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z');
}

static int is_name_char(char c) {
    return is_name_start(c) || (c >= '0' && c <= '9') || c == '.' || c == '-';
}

/* A number at p (which starts with a digit, a '-', or a '.' followed by a
 * digit). Returns its length, 0 when p holds no number.
 */
static size_t number_len(const char *p) {
    const char *q = p;
    if (*q == '-')
        q++;
    if (*q == '.')
        return (q[1] >= '0' && q[1] <= '9') ? 2 + strspn(q + 2, "0123456789") : 0;
    if (*q < '0' || *q > '9')
        return 0;
    q += strspn(q, "0123456789");
    if (*q == '.')
        q += 1 + strspn(q + 1, "0123456789");
    return (size_t)(q - p);
}

static char unescape(char c) {
    switch (c) {
    case 'n': return '\n';
    case 't': return '\t';
    case 'r': return '\r';
    case '"': return '"';
    case '\\': return '\\';
    case '0': return '\0';
    default: return c;
    }
}

Token *tokenize(Arena *a, const char *src, int *eline, int *ecol,
                char *err) {
    Lexer lx;
    const char *p = src;
    int line = 1, col = 1;
    lx.toks = NULL;
    lx.len = 0;
    lx.cap = 0;
    lx.a = a;
    *eline = 0;
    *ecol = 0;
    err[0] = '\0';

    while (*p) {
        if (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\f' || *p == '\v') {
            p++;
            col++;
        } else if (*p == '\n') {
            p++;
            line++;
            col = 1;
        } else if (*p == '#') {
            while (*p && *p != '\n') {
                p++;
                col++;
            }
        } else if (*p == '"') {
            int tline = line, tcol = col;
            int triple = p[0] == '"' && p[1] == '"' && p[2] == '"';
            const char *q;
            char *out, *w;
            q = p + (triple ? 3 : 1);
            out = arena_alloc(a, strlen(p) + 1);
            w = out;
            for (;;) {
                if (!*q || (!triple && *q == '\n')) {
                    *eline = tline;
                    *ecol = tcol;
                    snprintf(err, 512, "this string has no closing quote");
                    return NULL;
                }
                if (triple && q[0] == '"' && q[1] == '"' && q[2] == '"') {
                    q += 3;
                    break;
                }
                if (!triple && *q == '"') {
                    q++;
                    break;
                }
                if (*q == '\\' && q[1]) {
                    *w++ = unescape(q[1]);
                    if (q[1] == '\n') {
                        line++;
                        col = 1;
                    } else {
                        col += 2;
                    }
                    q += 2;
                    continue;
                }
                if (*q == '\n') {
                    line++;
                    col = 1;
                } else {
                    col++;
                }
                *w++ = *q++;
            }
            *w = '\0';
            col += triple ? 3 : 1;   /* the closing quote(s); body already counted */
            emit(&lx, T_STRING, out, 0, tline, tcol);
            p = q;
        } else if (is_name_start(*p)) {
            const char *q = p;
            int tcol = col;
            while (is_name_char(*q)) {
                q++;
                col++;
            }
            emit(&lx, T_NAME, arena_dupn(a, p, (size_t)(q - p)), 0, line, tcol);
            p = q;
        } else {
            size_t n = 0;
            if ((*p >= '0' && *p <= '9') || *p == '.' || *p == '-')
                n = number_len(p);
            if (n) {
                char *sp = arena_dupn(a, p, n);
                int tcol = col;
                emit(&lx, T_NUMBER, sp, strtod(sp, NULL), line, tcol);
                p += n;
                col += (int)n;
            } else if (*p == '(' || *p == ')' || *p == ',' || *p == '=' || *p == '*') {
                char one[2] = { *p, '\0' };
                emit(&lx, T_PUNCT, arena_dup(a, one), 0, line, col);
                p++;
                col++;
            } else {
                *eline = line;
                *ecol = col;
                snprintf(err, 512, "cannot read '%c' here", *p);
                return NULL;
            }
        }
    }
    emit(&lx, T_END, "", 0, line, col);
    return lx.toks;
}
