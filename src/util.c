/* Small shared pieces: arenas, output, errors, numbers. */
#include "omni.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ------------------------------------------------------------------- arena */
void arena_init(Arena *a) {
    a->head = NULL;
}

void *arena_alloc(Arena *a, size_t n) {
    size_t want;
    ArenaChunk *c;
    n = (n + 7) & ~(size_t)7;              /* keep everything aligned */
    c = a->head;
    if (!c || c->len + n > c->cap) {
        want = n > 4096 ? n : 4096;
        c = malloc(sizeof(ArenaChunk) + want);
        if (!c) {
            fprintf(stderr, "omni: out of memory\n");
            exit(1);
        }
        c->next = a->head;
        c->len = 0;
        c->cap = want;
        a->head = c;
    }
    c->len += n;
    return c->data + c->len - n;
}

char *arena_dupn(Arena *a, const char *s, size_t n) {
    char *out = arena_alloc(a, n + 1);
    memcpy(out, s, n);
    out[n] = '\0';
    return out;
}

char *arena_dup(Arena *a, const char *s) {
    return arena_dupn(a, s, strlen(s));
}

void arena_free(Arena *a) {
    ArenaChunk *c = a->head, *next;
    while (c) {
        next = c->next;
        free(c);
        c = next;
    }
    a->head = NULL;
}

/* ------------------------------------------------------------------ output */
void say(Interp *ip, const char *msg) {
    size_t n = strlen(msg);
    while (n && (msg[n - 1] == '\n' || msg[n - 1] == '\r'))
        n--;
    fwrite(msg, 1, n, ip->out);
    fputc('\n', ip->out);
    fflush(ip->out);
}

void say_text(Interp *ip, const char *text) {
    size_t n = strlen(text);
    if (!n)
        return;
    fwrite(text, 1, n, ip->out);
    if (text[n - 1] != '\n')
        fputc('\n', ip->out);
    fflush(ip->out);
}

/* ------------------------------------------------------------------- error */
void fail_at(Interp *ip, int line, int col, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(ip->errmsg, sizeof(ip->errmsg), fmt, ap);
    va_end(ap);
    ip->errline = line;
    ip->errcol = col;
    longjmp(ip->jb, 1);
}

const char *line_text(const char *src, int line, char *buf, size_t cap) {
    int cur = 1;
    const char *p = src, *start = src;
    if (line < 1 || cap == 0)
        return "";
    while (*p && cur < line) {
        if (*p == '\n') {
            cur++;
            start = p + 1;
        }
        p++;
    }
    if (cur != line)
        return "";
    p = start;
    while (*p && *p != '\n' && (size_t)(p - start) + 1 < cap) {
        buf[p - start] = *p;
        p++;
    }
    buf[p - start] = '\0';
    return buf;
}

/* ------------------------------------------------------------------ numbers */
void num_text(double num, int is_int, char *buf, size_t cap) {
    if (is_int)
        snprintf(buf, cap, "%lld", (long long)num);
    else
        snprintf(buf, cap, "%g", num);
}
