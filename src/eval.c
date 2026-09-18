/* The interpreter: statements to effects. */
#include "omni.h"

#include <ctype.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <direct.h>
#include <windows.h>
#define popen _popen
#define pclose _pclose
#define strdup _strdup
#else
#include <fcntl.h>
#include <poll.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#endif

#define DEFAULT_W 640
#define DEFAULT_H 400
#define DEFAULT_TITLE "OmniScript"
#define DEFAULT_BG "#0d1117"
#define FALLBACK_FILE "drawing.bmp"
#define BIGGEST 8000

/* ------------------------------------------------------------------ interp */
void interp_init(Interp *ip, FILE *out, const char *cwd) {
    memset(ip, 0, sizeof(*ip));
    ip->out = out;
    snprintf(ip->cwd, sizeof(ip->cwd), "%s", cwd);
    ip->gui_w = DEFAULT_W;
    ip->gui_h = DEFAULT_H;
    snprintf(ip->gui_title, sizeof(ip->gui_title), "%s", DEFAULT_TITLE);
    snprintf(ip->gui_bg, sizeof(ip->gui_bg), "%s", DEFAULT_BG);
}

static void free_node_heap(Node *n);
static void free_value_heap(Value *v);

static void free_value_heap(Value *v) {
    int i;
    if (!v)
        return;
    if ((v->kind == V_STR || v->kind == V_WORD) && v->str)
        free(v->str);
    for (i = 0; i < v->nitems; i++)
        free_value_heap(v->items[i]);
    free(v->items);
    free(v);
}

static void free_node_heap(Node *n) {
    int i;
    if (!n)
        return;
    free(n->text);
    for (i = 0; i < n->nargs; i++)
        free_node_heap(n->args[i]);
    free(n->args);
    free(n);
}

void gui_clear(Interp *ip) {
    GuiButton *b = ip->gui_buttons, *next;
    while (b) {
        int i;
        next = b->next;
        for (i = 0; i < E_SLOTS; i++)
            free_value_heap(b->el.slot[i]);
        free_node_heap(b->el.action);
        free(b);
        b = next;
    }
    ip->gui_buttons = NULL;
}

void interp_free(Interp *ip) {
    gui_clear(ip);
}

/* ------------------------------------------------------------ value basics */
static const char *vstr(Value *v, Interp *ip) {
    if (!v)
        return "";
    if (v->kind == V_NUM) {
        char buf[64];
        num_text(v->num, v->is_int, buf, sizeof(buf));
        return arena_dup(ip->arena, buf);
    }
    if (v->kind == V_TUPLE) {
        size_t cap = 64, len = 1;
        char *out = arena_alloc(ip->arena, cap);
        int i;
        out[0] = '(';
        for (i = 0; i < v->nitems; i++) {
            const char *s = vstr(v->items[i], ip);
            size_t n = strlen(s);
            while (len + n + 3 > cap) {
                char *bigger = arena_alloc(ip->arena, cap * 2);
                memcpy(bigger, out, len);
                out = bigger;
                cap *= 2;
            }
            if (i)
                out[len++] = ',';
            if (i)
                out[len++] = ' ';
            memcpy(out + len, s, n);
            len += n;
        }
        out[len++] = ')';
        out[len] = '\0';
        return out;
    }
    return v->str;
}

static double vnum(Value *v, double def, const char *what, int line, Interp *ip) {
    char *end;
    double d;
    if (!v)
        return def;
    if (v->kind == V_NUM)
        return v->num;
    if (v->kind == V_TUPLE)
        fail_at(ip, line, 0, "%s has to be a number, not %s", what, vstr(v, ip));
    d = strtod(v->str, &end);
    while (*end == ' ' || *end == '\t')
        end++;
    if (end == v->str || *end)
        fail_at(ip, line, 0, "%s has to be a number, not '%.100s'", what, v->str);
    return d;
}

static int vwhole(Value *v, int def, const char *what, int line, Interp *ip) {
    int n = (int)vnum(v, def, what, line, ip);
    if (n < -BIGGEST || n > BIGGEST)
        fail_at(ip, line, 0, "%s has to be between -%d and %d", what, BIGGEST, BIGGEST);
    return n;
}

/* Exposed to the GUI backends. */
int elem_num(Value *v, int def, const char *what, int line, Interp *ip) {
    return vwhole(v, def, what, line, ip);
}

const char *elem_str(Value *v, const char *def, Interp *ip) {
    if (!v)
        return def;
    return vstr(v, ip);
}

/* ------------------------------------------------------------------ colours */
static const struct {
    const char *name, *hex;
} NAMED[] = {
    { "black", "#000000" }, { "white", "#ffffff" }, { "red", "#e5534b" },
    { "green", "#2ea043" }, { "blue", "#58a6ff" }, { "yellow", "#f2cc60" },
    { "orange", "#f0883e" }, { "purple", "#a371f7" }, { "pink", "#ff7b9c" },
    { "cyan", "#39c5cf" }, { "teal", "#1f6feb" }, { "navy", "#0d1b3d" },
    { "grey", "#8b949e" }, { "gray", "#8b949e" }, { "silver", "#c9d1d9" },
    { "gold", "#e3b341" }, { "brown", "#8b5a2b" }, { "lime", "#7ee787" },
    { "maroon", "#8b2635" }, { "olive", "#7d8c34" },
    { NULL, NULL }
};

static int hexval(char c) {
    if (c >= '0' && c <= '9')
        return c - '0';
    if (c >= 'a' && c <= 'f')
        return c - 'a' + 10;
    if (c >= 'A' && c <= 'F')
        return c - 'A' + 10;
    return -1;
}

static void parse_rgb(Interp *ip, const char *given, int line,
                      const char *def, unsigned char out[3]) {
    char norm[64];
    size_t i, n;
    const char *s = given ? given : def;
    if (!s || !*s)
        s = def;
    n = strlen(s);
    if (n >= sizeof(norm))
        n = sizeof(norm) - 1;
    for (i = 0; i < n; i++)
        norm[i] = (char)tolower((unsigned char)s[i]);
    norm[n] = '\0';
    for (i = 0; NAMED[i].name; i++) {
        if (strcmp(norm, NAMED[i].name) == 0) {
            s = NAMED[i].hex;
            n = 7;
            memcpy(norm, s, 8);
            break;
        }
    }
    if (norm[0] == '#' && n == 7 && hexval(norm[1]) >= 0 && hexval(norm[2]) >= 0 &&
        hexval(norm[3]) >= 0 && hexval(norm[4]) >= 0 && hexval(norm[5]) >= 0 &&
        hexval(norm[6]) >= 0) {
        out[0] = (unsigned char)(hexval(norm[1]) * 16 + hexval(norm[2]));
        out[1] = (unsigned char)(hexval(norm[3]) * 16 + hexval(norm[4]));
        out[2] = (unsigned char)(hexval(norm[5]) * 16 + hexval(norm[6]));
        return;
    }
    if (norm[0] == '#' && n == 4 && hexval(norm[1]) >= 0 && hexval(norm[2]) >= 0 &&
        hexval(norm[3]) >= 0) {
        out[0] = (unsigned char)(hexval(norm[1]) * 17);
        out[1] = (unsigned char)(hexval(norm[2]) * 17);
        out[2] = (unsigned char)(hexval(norm[3]) * 17);
        return;
    }
    fail_at(ip, line, 0,
            "'%.100s' is not a colour: use #rrggbb, or one of black, blue, brown, "
            "cyan, gold, gray, green, grey, lime, maroon, navy, olive, orange, "
            "pink, purple, red, silver, teal, white, yellow",
            given ? given : "(nothing)");
}

static void elem_color(Value *v, int line, const char *def,
                       unsigned char out[3], Interp *ip) {
    const char *s = NULL;
    if (v && (v->kind == V_STR || v->kind == V_WORD))
        s = v->str;
    else if (v && v->kind == V_NUM)
        s = vstr(v, ip);
    parse_rgb(ip, s, line, def, out);
}

void elem_rgb(Value *v, int line, const char *def, unsigned char out[3],
              Interp *ip) {
    elem_color(v, line, def, out, ip);
}

/* ------------------------------------------------------------------ values */
static Value *new_value(Interp *ip, ValueKind kind) {
    Value *v = arena_alloc(ip->arena, sizeof(Value));
    memset(v, 0, sizeof(Value));
    v->kind = kind;
    return v;
}

Value *eval_command(Interp *ip, Node *node);

static Value *eval_value(Interp *ip, Node *node) {
    Value *v;
    int i;
    if (node->kind == ND_NUM) {
        v = new_value(ip, V_NUM);
        v->num = node->num;
        v->is_int = node->is_int;
        return v;
    }
    if (node->kind == ND_STR) {
        v = new_value(ip, V_STR);
        v->str = node->text;
        return v;
    }
    if (node->kind == ND_WORD) {
        v = new_value(ip, V_WORD);
        v->str = node->text;
        return v;
    }
    if (node->kind == ND_TUPLE) {
        v = new_value(ip, V_TUPLE);
        v->items = arena_alloc(ip->arena, sizeof(Value *) * (size_t)(node->nargs + 1));
        v->nitems = node->nargs;
        for (i = 0; i < node->nargs; i++)
            v->items[i] = eval_value(ip, node->args[i]);
        return v;
    }
    if (node->kind == ND_KWARG)
        return eval_value(ip, node->args[0]);
    return eval_command(ip, node);
}

/* Split a call's arguments into positional values and keywords. */
typedef struct {
    char *key;
    Value *val;
    int line, col;
} Kwarg;

static void call_args(Interp *ip, Node *node, Value ***pos, int *npos,
                      Kwarg **kws, int *nkws) {
    Value **p = arena_alloc(ip->arena, sizeof(Value *) * (size_t)(node->nargs + 1));
    Kwarg *k = arena_alloc(ip->arena, sizeof(Kwarg) * (size_t)(node->nargs + 1));
    int np = 0, nk = 0, i;
    for (i = 0; i < node->nargs; i++) {
        Node *a = node->args[i];
        if (a->kind == ND_KWARG) {
            int j;
            for (j = 0; j < nk; j++) {
                if (strcmp(k[j].key, a->text) == 0)
                    fail_at(ip, a->line, a->col, "%s() got '%s=' twice",
                            node->text, a->text);
            }
            k[nk].key = a->text;
            k[nk].val = eval_value(ip, a->args[0]);
            k[nk].line = a->line;
            k[nk].col = a->col;
            nk++;
        } else {
            if (nk)
                fail_at(ip, a->line, a->col,
                        "%s() has a positional argument after a keyword one",
                        node->text);
            p[np++] = eval_value(ip, a);
        }
    }
    *pos = p;
    *npos = np;
    *kws = k;
    *nkws = nk;
}

/* --------------------------------------------------------------------- cmd */
static Value *do_cmd(Interp *ip, Node *node, Value **args, int nargs, int nkws) {
    const char *command;
    int background = 0;
    int code;
    if (nkws)
        fail_at(ip, node->line, node->col,
                "cmd() takes no 'name=' arguments -- write cmd(\"...\") or "
                "cmd(background, \"...\")");
    if (!nargs)
        fail_at(ip, node->line, node->col,
                "cmd() needs a command to run, like cmd(\"tree /f\")");
    if (nargs > 1 && vstr(args[0], ip)[0]) {
        const char *first = vstr(args[0], ip);
        char low[32];
        size_t i;
        for (i = 0; i < sizeof(low) - 1 && first[i]; i++)
            low[i] = (char)tolower((unsigned char)first[i]);
        low[i] = '\0';
        background = strcmp(low, "background") == 0;
    }
    command = vstr(args[nargs - 1], ip);
    {
        const char *c = command;
        while (*c == ' ' || *c == '\t' || *c == '\n' || *c == '\r')
            c++;
        if (!*c)
            fail_at(ip, node->line, node->col, "cmd() was given an empty command");
    }
    if (background) {
#ifdef _WIN32
        char *cmdline;
        STARTUPINFOA si;
        PROCESS_INFORMATION pi;
        memset(&si, 0, sizeof(si));
        si.cb = sizeof(si);
        cmdline = arena_alloc(ip->arena, strlen(command) + 16);
        sprintf(cmdline, "cmd.exe /c %s", command);
        memset(&pi, 0, sizeof(pi));
        if (!CreateProcessA(NULL, cmdline, NULL, NULL, FALSE,
                            DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                            NULL, NULL, &si, &pi))
            fail_at(ip, node->line, node->col, "could not start '%.100s'", command);
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
        {
            char msg[256];
            snprintf(msg, sizeof(msg), "running in the background: %s (pid %ld)",
                     command, (long)pi.dwProcessId);
            say(ip, msg);
        }
        {
            Value *v = new_value(ip, V_NUM);
            v->num = (double)pi.dwProcessId;
            v->is_int = 1;
            return v;
        }
#else
        pid_t pid = fork();
        if (pid < 0)
            fail_at(ip, node->line, node->col, "could not start '%.100s': %s",
                    command, strerror(errno));
        if (pid == 0) {
            int devnull;
            setsid();
            devnull = open("/dev/null", O_RDWR);
            if (devnull >= 0) {
                dup2(devnull, 0);
                dup2(devnull, 1);
                dup2(devnull, 2);
                if (devnull > 2)
                    close(devnull);
            }
            execl("/bin/sh", "sh", "-c", command, (char *)NULL);
            _exit(127);
        }
        {
            char msg[1024];
            snprintf(msg, sizeof(msg), "running in the background: %s (pid %ld)",
                     command, (long)pid);
            say(ip, msg);
        }
        {
            Value *v = new_value(ip, V_NUM);
            v->num = (double)pid;
            v->is_int = 1;
            return v;
        }
#endif
    }
#ifdef _WIN32
    /* Windows pipes carry stdout only, so stderr joins it on the way. */
    {
        char *full = arena_alloc(ip->arena, strlen(command) + 8);
        FILE *pp;
        char *buf = arena_alloc(ip->arena, 4096);
        size_t cap = 4096, len = 0;
        sprintf(full, "%s 2>&1", command);
        pp = popen(full, "r");
        if (!pp)
            fail_at(ip, node->line, node->col, "could not run '%.100s': %s",
                    command, strerror(errno));
        for (;;) {
            size_t n;
            if (len + 1024 > cap) {
                char *bigger = arena_alloc(ip->arena, cap * 2);
                memcpy(bigger, buf, len);
                buf = bigger;
                cap *= 2;
            }
            n = fread(buf + len, 1, 1023, pp);
            len += n;
            if (n < 1023)
                break;
        }
        buf[len] = '\0';
        code = pclose(pp);
        if (len)
            say_text(ip, buf);
    }
#else
    /* Two pipes catch stdout and stderr apart, then both are said. */
    {
        int outp[2], errp[2];
        pid_t pid;
        char *obuf = arena_alloc(ip->arena, 4096);
        char *ebuf = arena_alloc(ip->arena, 4096);
        size_t ocap = 4096, olen = 0, ecap = 4096, elen = 0;
        struct pollfd fds[2];
        int live = 2, status;
        if (pipe(outp) != 0 || pipe(errp) != 0)
            fail_at(ip, node->line, node->col, "could not run '%.100s': %s",
                    command, strerror(errno));
        pid = fork();
        if (pid < 0) {
            close(outp[0]);
            close(outp[1]);
            close(errp[0]);
            close(errp[1]);
            fail_at(ip, node->line, node->col, "could not run '%.100s': %s",
                    command, strerror(errno));
        }
        if (pid == 0) {
            dup2(outp[1], 1);
            dup2(errp[1], 2);
            close(outp[0]);
            close(outp[1]);
            close(errp[0]);
            close(errp[1]);
            execl("/bin/sh", "sh", "-c", command, (char *)NULL);
            _exit(127);
        }
        close(outp[1]);
        close(errp[1]);
        fds[0].fd = outp[0];
        fds[0].events = POLLIN;
        fds[1].fd = errp[0];
        fds[1].events = POLLIN;
        while (live) {
            int i;
            if (poll(fds, 2, -1) < 0) {
                if (errno == EINTR)
                    continue;
                break;
            }
            for (i = 0; i < 2; i++) {
                if (fds[i].fd >= 0 &&
                    (fds[i].revents & (POLLIN | POLLHUP | POLLERR))) {
                    char tmp[4096];
                    ssize_t n = read(fds[i].fd, tmp, sizeof(tmp));
                    char **bufp = i == 0 ? &obuf : &ebuf;
                    size_t *capp = i == 0 ? &ocap : &ecap;
                    size_t *lenp = i == 0 ? &olen : &elen;
                    if (n > 0) {
                        while (*lenp + (size_t)n + 1 > *capp) {
                            char *b = arena_alloc(ip->arena, *capp * 2);
                            memcpy(b, *bufp, *lenp);
                            *bufp = b;
                            *capp *= 2;
                        }
                        memcpy(*bufp + *lenp, tmp, (size_t)n);
                        *lenp += (size_t)n;
                    } else {
                        close(fds[i].fd);
                        fds[i].fd = -1;
                        live--;
                    }
                }
            }
        }
        while (waitpid(pid, &status, 0) < 0 && errno == EINTR)
            ;
        code = WIFEXITED(status) ? WEXITSTATUS(status) : 1;
        obuf[olen] = '\0';
        ebuf[elen] = '\0';
        if (olen)
            say_text(ip, obuf);
        if (elen)
            say_text(ip, ebuf);
    }
#endif
    if (code) {
        char msg[64];
        snprintf(msg, sizeof(msg), "the command exited %d", code);
        say(ip, msg);
    }
    {
        Value *v = new_value(ip, V_NUM);
        v->num = (double)code;
        v->is_int = 1;
        return v;
    }
}

/* -------------------------------------------------------------------- file */
static void full_path(Interp *ip, const char *given, char *out, size_t cap) {
    int abs;
    size_t n = 0, i;
#ifdef _WIN32
    abs = (given[0] && given[1] == ':') || given[0] == '\\' || given[0] == '/';
#else
    abs = given[0] == '/';
#endif
    if (!abs) {
        for (i = 0; ip->cwd[i] && n + 1 < cap; i++)
            out[n++] = ip->cwd[i];
        if (n + 1 < cap)
#ifdef _WIN32
            out[n++] = '\\';
#else
            out[n++] = '/';
#endif
    }
    for (i = 0; given[i] && n + 1 < cap; i++)
        out[n++] = given[i];
    out[n] = '\0';
}

static char *read_file(Interp *ip, Node *node, const char *path, const char *shown) {
    FILE *f = fopen(path, "rb");
    char *buf;
    size_t cap = 4096, len = 0;
    (void)shown;
    if (!f) {
        const char *base = strrchr(path, '/');
#ifdef _WIN32
        {
            const char *b2 = strrchr(path, '\\');
            if (b2 && (!base || b2 > base))
                base = b2;
        }
#endif
        base = base ? base + 1 : path;
        if (errno == ENOENT)
            fail_at(ip, node->line, node->col, "%s is not there", base);
        fail_at(ip, node->line, node->col, "could not read %s: %s", base,
                strerror(errno));
    }
    buf = arena_alloc(ip->arena, cap);
    for (;;) {
        size_t n;
        if (len + 1024 > cap) {
            char *bigger = arena_alloc(ip->arena, cap * 2);
            memcpy(bigger, buf, len);
            buf = bigger;
            cap *= 2;
        }
        n = fread(buf + len, 1, 1023, f);
        len += n;
        if (n < 1023)
            break;
    }
    buf[len] = '\0';
    fclose(f);
    return buf;
}

static void make_parents(const char *path) {
    char tmp[4096];
    size_t i, n = strlen(path);
    if (n >= sizeof(tmp))
        return;
    memcpy(tmp, path, n + 1);
    for (i = 1; i < n; i++) {
        if (tmp[i] == '/' || tmp[i] == '\\') {
            char save = tmp[i];
            tmp[i] = '\0';
#ifdef _WIN32
            _mkdir(tmp);
#else
            mkdir(tmp, 0755);
#endif
            tmp[i] = save;
        }
    }
}

static Value *do_file(Interp *ip, Node *node, Value **args, int nargs, int nkws) {
    char action[16], path[4096], msg[512];
    const char *shown;
    size_t i;
    if (nkws)
        fail_at(ip, node->line, node->col,
                "file() takes no 'name=' arguments -- write "
                "file(create, \"a.txt\", \"hi\")");
    if (nargs < 2)
        fail_at(ip, node->line, node->col,
                "file() takes an action and a path, like "
                "file(create, \"a.txt\", \"hi\")");
    shown = vstr(args[1], ip);
    {
        const char *a = vstr(args[0], ip);
        for (i = 0; i < sizeof(action) - 1 && a[i]; i++)
            action[i] = (char)tolower((unsigned char)a[i]);
        action[i] = '\0';
    }
    full_path(ip, shown, path, sizeof(path));
    if (strcmp(action, "create") == 0) {
        const char *text = nargs > 2 ? vstr(args[2], ip) : "";
        FILE *f = fopen(path, "rb");
        if (f) {
            fclose(f);
            fail_at(ip, node->line, node->col,
                    "%.100s is already there -- file(edit, ...) changes it, "
                    "file(delete, ...) removes it", shown);
        }
        make_parents(path);
        f = fopen(path, "wb");
        if (!f)
            fail_at(ip, node->line, node->col, "could not write %.100s: %s",
                    shown, strerror(errno));
        fwrite(text, 1, strlen(text), f);
        fclose(f);
        snprintf(msg, sizeof(msg), "created %.100s (%lu bytes)", shown,
                 (unsigned long)strlen(text));
        say(ip, msg);
    } else if (strcmp(action, "edit") == 0) {
        const char *old, *newtext, *text, *hit;
        size_t occurrences = 0, oldlen, newlen, outlen;
        char *out, *w;
        if (nargs < 4)
            fail_at(ip, node->line, node->col,
                    "file(edit, path, old, new) needs the text to find and the text "
                    "to put there");
        old = vstr(args[2], ip);
        newtext = vstr(args[3], ip);
        text = read_file(ip, node, path, shown);
        oldlen = strlen(old);
        newlen = strlen(newtext);
        if (!oldlen)
            fail_at(ip, node->line, node->col, "file(edit, ...) cannot find nothing");
        for (hit = text; (hit = strstr(hit, old)); hit += oldlen)
            occurrences++;
        if (!occurrences)
            fail_at(ip, node->line, node->col, "%.100s has no '%.100s' in it to change",
                    shown, old);
        outlen = strlen(text) + occurrences * (newlen - oldlen);
        out = arena_alloc(ip->arena, outlen + 1);
        w = out;
        hit = text;
        for (;;) {
            const char *found = strstr(hit, old);
            if (!found) {
                strcpy(w, hit);
                break;
            }
            memcpy(w, hit, (size_t)(found - hit));
            w += found - hit;
            memcpy(w, newtext, newlen);
            w += newlen;
            hit = found + oldlen;
        }
        {
            FILE *f = fopen(path, "wb");
            if (!f)
                fail_at(ip, node->line, node->col, "could not write %.100s: %s",
                        shown, strerror(errno));
            fwrite(out, 1, outlen, f);
            fclose(f);
        }
        snprintf(msg, sizeof(msg), "edited %.100s (%lu place%s)", shown,
                 (unsigned long)occurrences, occurrences == 1 ? "" : "s");
        say(ip, msg);
    } else if (strcmp(action, "delete") == 0) {
        char *text = read_file(ip, node, path, shown);
        size_t n = strlen(text);
        if (remove(path) != 0)
            fail_at(ip, node->line, node->col, "could not delete %.100s: %s",
                    shown, strerror(errno));
        snprintf(msg, sizeof(msg), "deleted %.100s (%lu bytes)", shown,
                 (unsigned long)n);
        say(ip, msg);
    } else {
        fail_at(ip, node->line, node->col,
                "file() does create, edit, delete, not '%.100s'", action);
    }
    {
        Value *v = new_value(ip, V_STR);
        v->str = arena_dup(ip->arena, path);
        return v;
    }
}

/* ------------------------------------------------------------------- input */
static Value *do_input(Interp *ip, Node *node, Value **args, int nargs,
                       Kwarg *kws, int nkws) {
    const char *prompt = NULL;
    int i;
    size_t cap = 256, len = 0;
    char *line;
    int c, ended = 0;
    if (nargs > 1)
        fail_at(ip, node->line, node->col,
                "input() takes a prompt, like input(\"Name: \")");
    if (nargs == 1)
        prompt = vstr(args[0], ip);
    for (i = 0; i < nkws; i++) {
        char low[32];
        size_t k;
        for (k = 0; k < sizeof(low) - 1 && kws[i].key[k]; k++)
            low[k] = (char)tolower((unsigned char)kws[i].key[k]);
        low[k] = '\0';
        if (strcmp(low, "prompt") && strcmp(low, "text") && strcmp(low, "msg"))
            fail_at(ip, kws[i].line, kws[i].col,
                    "input() has no '%s=' -- it has prompt=", kws[i].key);
        if (prompt)
            fail_at(ip, kws[i].line, kws[i].col,
                    "input() got the prompt twice");
        prompt = vstr(kws[i].val, ip);
    }
    if (prompt && *prompt) {
        fwrite(prompt, 1, strlen(prompt), ip->out);
        fflush(ip->out);
    }
    line = arena_alloc(ip->arena, cap);
    for (;;) {
        c = fgetc(stdin);
        if (c == EOF) {
            ended = 1;
            break;
        }
        if (c == '\n')
            break;
        if (len + 1 >= cap) {
            char *bigger = arena_alloc(ip->arena, cap * 2);
            memcpy(bigger, line, len);
            line = bigger;
            cap *= 2;
        }
        line[len++] = (char)c;
    }
    line[len] = '\0';
    if (len && line[len - 1] == '\r')
        line[--len] = '\0';
    if (ended && !len)
        fail_at(ip, node->line, node->col,
                "input() reached the end with nothing typed");
    {
        char *msg = arena_alloc(ip->arena, len + 16);
        sprintf(msg, "typed: %s", line);
        say(ip, msg);
    }
    {
        Value *v = new_value(ip, V_STR);
        v->str = line;
        return v;
    }
}

/* -------------------------------------------------------- element keywords */
typedef struct {
    const char *name;
    const char *slots[8];
    int nslots;
    const char *aliases[12][2];
    int naliases;
} ElemSpec;

static const ElemSpec SPECS[] = {
    { "window", { "width", "height", "title", "background" }, 4,
      { { "w", "width" }, { "h", "height" }, { "name", "title" },
        { "bg", "background" }, { "color", "background" }, { "colour", "background" } }, 6 },
    { "window_size", { "width", "height", "title", "background" }, 4,
      { { "w", "width" }, { "h", "height" }, { "name", "title" },
        { "bg", "background" }, { "color", "background" }, { "colour", "background" } }, 6 },
    { "rect", { "x", "y", "width", "height", "color" }, 5,
      { { "w", "width" }, { "h", "height" }, { "bg", "color" },
        { "colour", "color" }, { "fill", "color" } }, 5 },
    { "circle", { "x", "y", "radius", "color" }, 4,
      { { "r", "radius" }, { "bg", "color" },
        { "colour", "color" }, { "fill", "color" } }, 4 },
    { "line", { "x1", "y1", "x2", "y2", "color", "width" }, 6,
      { { "colour", "color" }, { "w", "width" }, { "thickness", "width" } }, 3 },
    { "text", { "x", "y", "message", "color", "size" }, 5,
      { { "text", "message" }, { "msg", "message" }, { "string", "message" },
        { "content", "message" }, { "colour", "color" }, { "font_size", "size" } }, 6 },
    { "button", { "x", "y", "width", "height", "label" }, 5,
      { { "w", "width" }, { "h", "height" }, { "text", "label" },
        { "title", "label" }, { "caption", "label" }, { "name", "label" } }, 6 },
    { "save", { "path" }, 1,
      { { "file", "path" }, { "filename", "path" },
        { "to", "path" }, { "name", "path" } }, 4 },
    { NULL, { NULL }, 0, { { NULL, NULL } }, 0 }
};

static const ElemSpec *spec_of(const char *name) {
    int i;
    for (i = 0; SPECS[i].name; i++) {
        if (strcmp(SPECS[i].name, name) == 0)
            return &SPECS[i];
    }
    return NULL;
}

static const char *PAIR_POS[] = { "rect", "circle", "text", "button", NULL };
static const char *PAIR_SIZE[] = { "rect", "button", "window", "window_size", NULL };
static const char *PAIR_FROM[] = { "line", NULL };

static int pair_allowed(const char *pair, const char *kind) {
    const char **list = NULL;
    int i;
    if (strcmp(pair, "pos") == 0)
        list = PAIR_POS;
    else if (strcmp(pair, "size") == 0)
        list = PAIR_SIZE;
    else if (strcmp(pair, "from") == 0 || strcmp(pair, "to") == 0)
        list = PAIR_FROM;
    else
        return 0;
    for (i = 0; list[i]; i++) {
        if (strcmp(list[i], kind) == 0)
            return 1;
    }
    return 0;
}

static int is_action_key(const char *key) {
    char low[32];
    size_t i;
    for (i = 0; i < sizeof(low) - 1 && key[i]; i++)
        low[i] = (char)tolower((unsigned char)key[i]);
    low[i] = '\0';
    return strcmp(low, "action") == 0 || strcmp(low, "command") == 0 ||
           strcmp(low, "on_click") == 0 || strcmp(low, "do") == 0;
}

static void lower_key(const char *key, char *out, size_t cap) {
    size_t i;
    for (i = 0; i + 1 < cap && key[i]; i++)
        out[i] = (char)tolower((unsigned char)key[i]);
    out[i] = '\0';
}

/* Two numbers out of a tuple or a "20, 30" / "800x600" string. */
static void as_pair(Interp *ip, const char *ename, const char *pair,
                    Value *v, int line, int col, Value **first, Value **second) {
    char what[64];
    snprintf(what, sizeof(what), "%s's %s", ename, pair);
    if (v->kind == V_TUPLE && v->nitems == 2) {
        *first = v->items[0];
        *second = v->items[1];
        return;
    }
    if (v->kind == V_STR || v->kind == V_WORD) {
        char tmp[128], *parts[2];
        size_t i, n = 0;
        snprintf(tmp, sizeof(tmp), "%.127s", v->str);
        for (i = 0; tmp[i]; i++) {
            tmp[i] = (char)tolower((unsigned char)tmp[i]);
            if (tmp[i] == 'x' || tmp[i] == ';')
                tmp[i] = ',';
        }
        for (i = 0; tmp[i];) {
            while (tmp[i] == ',' || tmp[i] == ' ' || tmp[i] == '\t')
                i++;
            if (!tmp[i] || n == 2)
                break;
            parts[n++] = &tmp[i];
            while (tmp[i] && tmp[i] != ',' && tmp[i] != ' ' && tmp[i] != '\t')
                i++;
            if (tmp[i])
                tmp[i++] = '\0';
        }
        if (n == 2 && !tmp[i]) {
            Value *a = new_value(ip, V_STR);
            Value *b = new_value(ip, V_STR);
            a->str = arena_dup(ip->arena, parts[0]);
            b->str = arena_dup(ip->arena, parts[1]);
            *first = a;
            *second = b;
            return;
        }
    }
    fail_at(ip, line, col, "%s has to be two numbers, like (20, 30)", what);
}

static int slot_index(const ElemSpec *spec, const char *slot) {
    int i;
    for (i = 0; i < spec->nslots; i++) {
        if (strcmp(spec->slots[i], slot) == 0)
            return i;
    }
    return -1;
}

static const char *alias_of(const ElemSpec *spec, const char *key) {
    int i;
    for (i = 0; i < spec->naliases; i++) {
        if (strcmp(spec->aliases[i][0], key) == 0)
            return spec->aliases[i][1];
    }
    return key;
}

/* Positional values plus keywords resolved onto slots. */
static void resolve_kwargs(Interp *ip, const ElemSpec *spec, const char *ename,
                           Value **pos, int npos, Kwarg *kws, int nkws,
                           int line, int col, Value **slots) {
    int i, nfilled = npos;
    Value *pos_pair[4][2];   /* pos, size, from, to */
    int have_pair[4] = { 0, 0, 0, 0 };
    const char *pair_names[4] = { "pos", "size", "from", "to" };
    for (i = 0; i < E_SLOTS; i++)
        slots[i] = NULL;
    for (i = 0; i < npos && i < E_SLOTS; i++)
        slots[i] = pos[i];
    /* Pairs first, but only where they mean something. */
    for (i = 0; i < nkws; i++) {
        char low[32];
        int which;
        lower_key(kws[i].key, low, sizeof(low));
        for (which = 0; which < 4; which++) {
            if (strcmp(low, pair_names[which]) == 0 &&
                pair_allowed(low, ename)) {
                if (have_pair[which])
                    fail_at(ip, kws[i].line, kws[i].col, "%s() got '%s=' twice",
                            ename, kws[i].key);
                as_pair(ip, ename, low, kws[i].val, kws[i].line, kws[i].col,
                        &pos_pair[which][0], &pos_pair[which][1]);
                have_pair[which] = 1;
                kws[i].key = NULL;   /* consumed */
                break;
            }
        }
    }
    /* Place pairs onto slots. */
    {
        struct {
            int which;
            const char *a, *b;
        } maps[4];
        int nmaps = 0;
        if (!strcmp(ename, "rect") || !strcmp(ename, "circle") ||
            !strcmp(ename, "text") || !strcmp(ename, "button")) {
            maps[nmaps].which = 0;
            maps[nmaps].a = "x";
            maps[nmaps].b = "y";
            nmaps++;
        }
        if (!strcmp(ename, "rect") || !strcmp(ename, "button") ||
            !strcmp(ename, "window") || !strcmp(ename, "window_size")) {
            maps[nmaps].which = 1;
            if (!strcmp(ename, "window") || !strcmp(ename, "window_size")) {
                maps[nmaps].a = "width";
                maps[nmaps].b = "height";
            } else {
                maps[nmaps].a = "width";
                maps[nmaps].b = "height";
            }
            nmaps++;
        }
        if (!strcmp(ename, "line")) {
            maps[nmaps].which = 2;
            maps[nmaps].a = "x1";
            maps[nmaps].b = "y1";
            nmaps++;
            maps[nmaps].which = 3;
            maps[nmaps].a = "x2";
            maps[nmaps].b = "y2";
            nmaps++;
        }
        for (i = 0; i < nmaps; i++) {
            int w = maps[i].which;
            int ia, ib;
            if (!have_pair[w])
                continue;
            ia = slot_index(spec, maps[i].a);
            ib = slot_index(spec, maps[i].b);
            if (ia < nfilled || ib < nfilled)
                fail_at(ip, line, col, "%s() got '%s' twice (positionally and as %s=)",
                        ename, ia < nfilled ? maps[i].a : maps[i].b,
                        pair_names[w]);
            while (nfilled < ia)
                slots[nfilled++] = NULL;
            slots[nfilled++] = pos_pair[w][0];
            while (nfilled < ib)
                slots[nfilled++] = NULL;
            slots[nfilled++] = pos_pair[w][1];
        }
    }
    for (i = 0; i < nkws; i++) {
        char low[32];
        const char *slot;
        int idx;
        if (!kws[i].key)
            continue;
        lower_key(kws[i].key, low, sizeof(low));
        slot = alias_of(spec, low);
        idx = slot_index(spec, slot);
        if (idx < 0) {
            char known[256], *w = known;
            size_t left = sizeof(known);
            int j, n;
            for (j = 0; j < spec->nslots; j++) {
                n = snprintf(w, left, "%s%s", j ? ", " : "", spec->slots[j]);
                w += n;
                left -= (size_t)n;
            }
            for (j = 0; j < 4; j++) {
                if (pair_allowed(pair_names[j], ename)) {
                    n = snprintf(w, left, ", %s", pair_names[j]);
                    w += n;
                    left -= (size_t)n;
                }
            }
            if (!strcmp(ename, "button")) {
                n = snprintf(w, left, ", action");
                w += n;
                left -= (size_t)n;
            }
            (void)left;
            fail_at(ip, kws[i].line, kws[i].col, "%s() has no '%s=' -- it has %s",
                    ename, kws[i].key, known);
        }
        if (idx < nfilled)
            fail_at(ip, kws[i].line, kws[i].col,
                    "%s() got '%s' twice (positionally and as '%s=')", ename,
                    slot, kws[i].key);
        while (nfilled < idx)
            slots[nfilled++] = NULL;
        slots[nfilled++] = kws[i].val;
    }
    /* window_size("800x600") and window_size((800, 600)) both fit. */
    if ((!strcmp(ename, "window") || !strcmp(ename, "window_size")) && nfilled == 1) {
        if (slots[0] && slots[0]->kind == V_TUPLE) {
            if (slots[0]->nitems != 2)
                fail_at(ip, line, col,
                        "window_size() takes a width and a height, like "
                        "window_size(800, 600)");
            slots[1] = slots[0]->items[1];
            slots[0] = slots[0]->items[0];
            nfilled = 2;
        } else if (slots[0] && slots[0]->kind != V_NUM) {
            Value *a, *b;
            as_pair(ip, ename, "size", slots[0], line, col, &a, &b);
            slots[0] = a;
            slots[1] = b;
            nfilled = 2;
        }
    }
    if (!strcmp(ename, "button") && !slots[4]) {
        Value *v = new_value(ip, V_STR);
        v->str = "button";
        slots[4] = v;
    }
    if (!strcmp(ename, "text") && !slots[2]) {
        Value *v = new_value(ip, V_STR);
        v->str = "";
        slots[2] = v;
    }
}

/* ------------------------------------------------------------- the elements */
static ElemKind elem_kind_of(const char *name) {
    if (!strcmp(name, "window") || !strcmp(name, "window_size"))
        return E_WINDOW;
    if (!strcmp(name, "rect"))
        return E_RECT;
    if (!strcmp(name, "circle"))
        return E_CIRCLE;
    if (!strcmp(name, "line"))
        return E_LINE;
    if (!strcmp(name, "text"))
        return E_TEXT;
    if (!strcmp(name, "button"))
        return E_BUTTON;
    return E_SAVE;
}

static int is_element(const char *name) {
    return spec_of(name) != NULL;
}

static int is_command(const char *name) {
    return !strcmp(name, "draw") || !strcmp(name, "draw_gui") ||
           !strcmp(name, "cmd") || !strcmp(name, "file") || !strcmp(name, "input");
}

static Element make_element(Interp *ip, const char *ename, Node *node) {
    const ElemSpec *spec = spec_of(ename);
    Element el;
    Value **pos;
    int npos = 0, i, last;
    Kwarg *kws;
    int nkws = 0;
    Node *action = NULL;
    memset(&el, 0, sizeof(el));
    el.kind = elem_kind_of(ename);
    el.line = node->line;
    pos = arena_alloc(ip->arena, sizeof(Value *) * (size_t)(node->nargs + 1));
    kws = arena_alloc(ip->arena, sizeof(Kwarg) * (size_t)(node->nargs + 1));
    last = node->nargs - 1;
    for (i = 0; i < node->nargs; i++) {
        Node *a = node->args[i];
        if (a->kind == ND_KWARG) {
            int act = !strcmp(ename, "button") && is_action_key(a->text);
            int j;
            if (act) {
                if (action)
                    fail_at(ip, a->line, a->col, "%s() got '%s=' twice", ename,
                            a->text);
                if (a->args[0]->kind != ND_CALL)
                    fail_at(ip, a->line, a->col,
                            "a button's action has to be a command, like "
                            "action=cmd(\"ls\")");
                action = a->args[0];
                continue;
            }
            for (j = 0; j < nkws; j++) {
                if (kws[j].key && !strcmp(kws[j].key, a->text))
                    fail_at(ip, a->line, a->col, "%s() got '%s=' twice", ename,
                            a->text);
            }
            kws[nkws].key = a->text;
            kws[nkws].val = eval_value(ip, a->args[0]);
            kws[nkws].line = a->line;
            kws[nkws].col = a->col;
            nkws++;
        } else {
            if (nkws || action)
                fail_at(ip, a->line, a->col,
                        "%s() has a positional argument after a keyword one", ename);
            if (!strcmp(ename, "button") && i == last && a->kind == ND_CALL)
                action = a;
            else
                pos[npos++] = eval_value(ip, a);
        }
    }
    resolve_kwargs(ip, spec, ename, pos, npos, kws, nkws, node->line, node->col,
                   el.slot);
    el.action = action;
    return el;
}

static Element parse_element(Interp *ip, Node *node) {
    const char *kind;
    if (node->kind != ND_CALL)
        fail_at(ip, node->line, node->col,
                "draw() and draw_gui() take elements: window(), window_size(), "
                "rect(), circle(), line(), text(), button(), save()");
    kind = node->text;
    if (!strcmp(kind, "draw_gui.button") || !strcmp(kind, "draw_gui.window_size")) {
        const char *shortname = strchr(kind, '.') + 1;
        fail_at(ip, node->line, node->col,
                "%s(...) is a command -- inside draw() write %s(...) without the prefix",
                kind, shortname);
    }
    if (!is_element(kind)) {
        if (is_command(kind))
            fail_at(ip, node->line, node->col,
                    "%s() is a command, not something draw() can place", kind);
        fail_at(ip, node->line, node->col,
                "draw() has no element called %s -- it has window, window_size, "
                "rect, circle, line, text, button, save", kind);
    }
    return make_element(ip, kind, node);
}

/* ----------------------------------------------------------------- painting */
static void paint_button(Canvas *c, Element *el, Interp *ip) {
    int x = vwhole(el->slot[0], 0, "button's x", el->line, ip);
    int y = vwhole(el->slot[1], 0, "button's y", el->line, ip);
    int w = vwhole(el->slot[2], 120, "button's width", el->line, ip);
    int h = vwhole(el->slot[3], 32, "button's height", el->line, ip);
    const char *label = elem_str(el->slot[4], "button", ip);
    unsigned char face[3], edge[3], ink[3];
    int size, tw;
    parse_rgb(ip, "#21262d", el->line, "#21262d", face);
    parse_rgb(ip, "#8b949e", el->line, "#8b949e", edge);
    parse_rgb(ip, "#ffffff", el->line, "#ffffff", ink);
    canvas_rect(c, x, y, w, h, face);
    canvas_outline(c, x, y, w, h, edge);
    size = h - 8;
    if (size > 14)
        size = 14;
    if (size < 8)
        size = 8;
    tw = canvas_text_width(label, size);
    {
        int tx = x + (w - tw) / 2;
        int ty = y + (h - size) / 2;
        if (tx < x + 4)
            tx = x + 4;
        if (ty < y + 2)
            ty = y + 2;
        canvas_text(c, tx, ty, label, ink, size);
    }
}

static Canvas *paint(Interp *ip, Element *elems, int nelems, int w, int h,
                     const unsigned char bg[3]) {
    Canvas *c = canvas_new(w, h, bg);
    int i;
    if (!c)
        fail_at(ip, 0, 0, "out of memory");
    for (i = 0; i < nelems; i++) {
        Element *el = &elems[i];
        unsigned char col[3];
        switch (el->kind) {
        case E_RECT:
            elem_color(el->slot[4], el->line, "#58a6ff", col, ip);
            canvas_rect(c, vwhole(el->slot[0], 0, "rect's x", el->line, ip),
                        vwhole(el->slot[1], 0, "rect's y", el->line, ip),
                        vwhole(el->slot[2], 0, "rect's width", el->line, ip),
                        vwhole(el->slot[3], 0, "rect's height", el->line, ip), col);
            break;
        case E_CIRCLE:
            elem_color(el->slot[3], el->line, "#58a6ff", col, ip);
            canvas_circle(c, vwhole(el->slot[0], 0, "circle's x", el->line, ip),
                          vwhole(el->slot[1], 0, "circle's y", el->line, ip),
                          vwhole(el->slot[2], 0, "circle's radius", el->line, ip),
                          col);
            break;
        case E_LINE:
            elem_color(el->slot[4], el->line, "#58a6ff", col, ip);
            canvas_line(c, vwhole(el->slot[0], 0, "line's x1", el->line, ip),
                        vwhole(el->slot[1], 0, "line's y1", el->line, ip),
                        vwhole(el->slot[2], 0, "line's x2", el->line, ip),
                        vwhole(el->slot[3], 0, "line's y2", el->line, ip), col,
                        vwhole(el->slot[5], 1, "line's width", el->line, ip));
            break;
        case E_TEXT:
            elem_color(el->slot[3], el->line, "#58a6ff", col, ip);
            canvas_text(c, vwhole(el->slot[0], 0, "text's x", el->line, ip),
                        vwhole(el->slot[1], 0, "text's y", el->line, ip),
                        elem_str(el->slot[2], "", ip), col,
                        vwhole(el->slot[4], 14, "text's size", el->line, ip));
            break;
        case E_BUTTON:
            paint_button(c, el, ip);
            break;
        default:
            break;
        }
    }
    return c;
}

/* --------------------------------------------------------------- rendering */
static Value *render_elements(Interp *ip, Element *elems, int nelems,
                              int line, int col) {
    int w = DEFAULT_W, h = DEFAULT_H, win_line = 0;
    const char *title = DEFAULT_TITLE, *save_to = NULL;
    const char *bg_given = DEFAULT_BG;
    unsigned char bg[3];
    int i;
    for (i = 0; i < nelems; i++) {
        if (elems[i].kind == E_WINDOW) {
            w = vwhole(elems[i].slot[0], DEFAULT_W, "the window's width",
                       elems[i].line, ip);
            h = vwhole(elems[i].slot[1], DEFAULT_H, "the window's height",
                       elems[i].line, ip);
            if (elems[i].slot[2]) {
                const char *t = vstr(elems[i].slot[2], ip);
                if (*t)
                    title = t;
            }
            if (elems[i].slot[3])
                bg_given = vstr(elems[i].slot[3], ip);
            win_line = elems[i].line;
        } else if (elems[i].kind == E_SAVE) {
            if (!elems[i].slot[0])
                fail_at(ip, elems[i].line, col, "save() needs a file name");
            save_to = vstr(elems[i].slot[0], ip);
        }
    }
    if (w < 1 || h < 1)
        fail_at(ip, line, col, "a window cannot be %dx%d", w, h);
    parse_rgb(ip, bg_given, win_line ? win_line : line, DEFAULT_BG, bg);
    if (save_to) {
        Canvas *c = paint(ip, elems, nelems, w, h, bg);
        char path[4096], msg[512];
        full_path(ip, save_to, path, sizeof(path));
        make_parents(path);
        if (img_write_bmp(path, c) != 0) {
            int e = errno;
            canvas_free(c);
            fail_at(ip, line, col, "could not write %.100s: %s", save_to,
                    strerror(e));
        }
        canvas_free(c);
        snprintf(msg, sizeof(msg), "wrote %s (%dx%d)", save_to, w, h);
        say(ip, msg);
        {
            Value *v = new_value(ip, V_STR);
            v->str = arena_dup(ip->arena, path);
            return v;
        }
    }
    if (gui_available() && gui_show(ip, elems, nelems, w, h, title, bg))
        return NULL;
    {
        Canvas *c = paint(ip, elems, nelems, w, h, bg);
        char path[4096], msg[512];
        full_path(ip, FALLBACK_FILE, path, sizeof(path));
        if (img_write_bmp(path, c) != 0) {
            int e = errno;
            canvas_free(c);
            fail_at(ip, line, col, "could not write %s: %s", FALLBACK_FILE,
                    strerror(e));
        }
        canvas_free(c);
        snprintf(msg, sizeof(msg), "there is no window here, so wrote %s (%dx%d)",
                 FALLBACK_FILE, w, h);
        say(ip, msg);
        {
            Value *v = new_value(ip, V_STR);
            v->str = arena_dup(ip->arena, path);
            return v;
        }
    }
}

static Value *do_draw(Interp *ip, Node *node) {
    Element *elems;
    int i;
    if (!node->nargs)
        fail_at(ip, node->line, node->col,
                "draw() needs something to draw, like draw(window(200, 100, \"Hi\"))");
    elems = arena_alloc(ip->arena, sizeof(Element) * (size_t)node->nargs);
    for (i = 0; i < node->nargs; i++)
        elems[i] = parse_element(ip, node->args[i]);
    return render_elements(ip, elems, node->nargs, node->line, node->col);
}

/* ---------------------------------------------------------------- draw_gui */
static Node *copy_node_heap(Node *n) {
    Node *c;
    int i;
    if (!n)
        return NULL;
    c = malloc(sizeof(Node));
    memcpy(c, n, sizeof(Node));
    c->text = n->text ? strdup(n->text) : NULL;
    c->from_base = n->from_base ? strdup(n->from_base) : NULL;
    c->args = n->nargs ? malloc(sizeof(Node *) * (size_t)n->nargs) : NULL;
    for (i = 0; i < n->nargs; i++)
        c->args[i] = copy_node_heap(n->args[i]);
    c->imports = NULL;
    c->nimports = 0;
    return c;
}

static Value *copy_value_heap(Value *v) {
    Value *c;
    int i;
    if (!v)
        return NULL;
    c = malloc(sizeof(Value));
    memcpy(c, v, sizeof(Value));
    c->str = v->str ? strdup(v->str) : NULL;
    c->items = v->nitems ? malloc(sizeof(Value *) * (size_t)v->nitems) : NULL;
    for (i = 0; i < v->nitems; i++)
        c->items[i] = copy_value_heap(v->items[i]);
    return c;
}

static Value *do_gui_window_size(Interp *ip, Node *node) {
    const ElemSpec *spec = spec_of("window_size");
    Value **pos;
    int npos = 0, i;
    Kwarg *kws;
    int nkws = 0;
    Value *slots[E_SLOTS];
    int w, h;
    const char *title, *bg_given;
    unsigned char bg[3];
    char msg[512];
    pos = arena_alloc(ip->arena, sizeof(Value *) * (size_t)(node->nargs + 1));
    kws = arena_alloc(ip->arena, sizeof(Kwarg) * (size_t)(node->nargs + 1));
    for (i = 0; i < node->nargs; i++) {
        Node *a = node->args[i];
        if (a->kind == ND_KWARG) {
            int j;
            for (j = 0; j < nkws; j++) {
                if (!strcmp(kws[j].key, a->text))
                    fail_at(ip, a->line, a->col, "window_size() got '%s=' twice",
                            a->text);
            }
            kws[nkws].key = a->text;
            kws[nkws].val = eval_value(ip, a->args[0]);
            kws[nkws].line = a->line;
            kws[nkws].col = a->col;
            nkws++;
        } else {
            if (nkws)
                fail_at(ip, a->line, a->col,
                        "window_size() has a positional argument after a keyword one");
            pos[npos++] = eval_value(ip, a);
        }
    }
    resolve_kwargs(ip, spec, "window_size", pos, npos, kws, nkws, node->line,
                   node->col, slots);
    w = vwhole(slots[0], DEFAULT_W, "the window's width", node->line, ip);
    h = vwhole(slots[1], DEFAULT_H, "the window's height", node->line, ip);
    if (w < 1 || h < 1)
        fail_at(ip, node->line, node->col, "a window cannot be %dx%d", w, h);
    title = DEFAULT_TITLE;
    if (slots[2]) {
        const char *t = vstr(slots[2], ip);
        if (*t)
            title = t;
    }
    bg_given = DEFAULT_BG;
    if (slots[3]) {
        const char *b = vstr(slots[3], ip);
        if (*b)
            bg_given = b;
    }
    parse_rgb(ip, bg_given, node->line, DEFAULT_BG, bg);
    ip->gui_w = w;
    ip->gui_h = h;
    snprintf(ip->gui_title, sizeof(ip->gui_title), "%s", title);
    snprintf(ip->gui_bg, sizeof(ip->gui_bg), "#%02x%02x%02x", bg[0], bg[1], bg[2]);
    snprintf(msg, sizeof(msg), "window size %dx%d \"%s\"", w, h, title);
    say(ip, msg);
    {
        Value *v = new_value(ip, V_TUPLE);
        Value *a = new_value(ip, V_NUM);
        Value *b = new_value(ip, V_NUM);
        a->num = w;
        a->is_int = 1;
        b->num = h;
        b->is_int = 1;
        v->items = arena_alloc(ip->arena, sizeof(Value *) * 2);
        v->items[0] = a;
        v->items[1] = b;
        v->nitems = 2;
        return v;
    }
}

static Value *do_gui_button(Interp *ip, Node *node) {
    Element el = make_element(ip, "button", node);
    GuiButton *b = malloc(sizeof(GuiButton));
    GuiButton **tail;
    char msg[512], at[64];
    int i;
    memset(b, 0, sizeof(*b));
    b->el.kind = E_BUTTON;
    b->el.line = el.line;
    for (i = 0; i < E_SLOTS; i++)
        b->el.slot[i] = copy_value_heap(el.slot[i]);
    b->el.action = copy_node_heap(el.action);
    tail = &ip->gui_buttons;
    while (*tail)
        tail = &(*tail)->next;
    *tail = b;
    {
        int x = el.slot[0] && el.slot[0]->kind == V_NUM ? (int)el.slot[0]->num : 0;
        int y = el.slot[1] && el.slot[1]->kind == V_NUM ? (int)el.slot[1]->num : 0;
        snprintf(at, sizeof(at), "(%d, %d)", x, y);
    }
    snprintf(msg, sizeof(msg), "added button '%.100s' at %s",
             elem_str(el.slot[4], "button", ip), at);
    say(ip, msg);
    {
        Value *v = new_value(ip, V_STR);
        v->str = arena_dup(ip->arena, elem_str(el.slot[4], "button", ip));
        return v;
    }
}

static Value *do_draw_gui(Interp *ip, Node *node) {
    Element *elems;
    int i, nqueued = 0, total, at = 0;
    GuiButton *b;
    int has_window = 0;
    Value *result;
    for (b = ip->gui_buttons; b; b = b->next)
        nqueued++;
    total = node->nargs + nqueued + 1;
    elems = arena_alloc(ip->arena, sizeof(Element) * (size_t)total);
    {
        Element *explicit = arena_alloc(ip->arena,
                                        sizeof(Element) * (size_t)(node->nargs + 1));
        for (i = 0; i < node->nargs; i++) {
            explicit[i] = parse_element(ip, node->args[i]);
            if (explicit[i].kind == E_WINDOW)
                has_window = 1;
        }
        /* Order: the remembered window (when none is given), the queued
         * buttons, then this call's own elements.
         */
        if (!has_window) {
            Element win;
            Value *title, *bg;
            memset(&win, 0, sizeof(win));
            win.kind = E_WINDOW;
            win.line = node->line;
            win.slot[0] = new_value(ip, V_NUM);
            win.slot[0]->num = ip->gui_w;
            win.slot[0]->is_int = 1;
            win.slot[1] = new_value(ip, V_NUM);
            win.slot[1]->num = ip->gui_h;
            win.slot[1]->is_int = 1;
            title = new_value(ip, V_STR);
            title->str = arena_dup(ip->arena, ip->gui_title);
            win.slot[2] = title;
            bg = new_value(ip, V_STR);
            bg->str = arena_dup(ip->arena, ip->gui_bg);
            win.slot[3] = bg;
            elems[at++] = win;
        }
        for (b = ip->gui_buttons; b; b = b->next)
            elems[at++] = b->el;   /* render only reads them */
        for (i = 0; i < node->nargs; i++)
            elems[at++] = explicit[i];
    }
    result = render_elements(ip, elems, at, node->line, node->col);
    gui_clear(ip);
    return result;
}

/* A button click runs its command; a failure is said, not raised. */
void gui_fire(Interp *ip, Node *action, const char *label) {
    Arena arena;
    char clicked[512];
    if (!action)
        return;
    snprintf(clicked, sizeof(clicked), "clicked '%.400s'", label ? label : "button");
    say(ip, clicked);
    Arena *outer = ip->arena;
    char saved_msg[1024];
    jmp_buf saved_jb;
    arena_init(&arena);
    ip->arena = &arena;
    memcpy(saved_jb, ip->jb, sizeof(jmp_buf));
    memcpy(saved_msg, ip->errmsg, sizeof(saved_msg));
    if (setjmp(ip->jb)) {
        char linebuf[512], msg[2048];
        fprintf(ip->out, "%s", "");
        snprintf(msg, sizeof(msg), "%s:%d: %s", ip->name, ip->errline, ip->errmsg);
        say(ip, msg);
        if (line_text(ip->source, ip->errline, linebuf, sizeof(linebuf))[0]) {
            int i, col = ip->errcol > 0 ? ip->errcol - 1 : 0;
            fprintf(ip->out, "    %s\n    ", linebuf);
            for (i = 0; i < col; i++)
                fputc(' ', ip->out);
            fprintf(ip->out, "^\n");
            fflush(ip->out);
        }
        memcpy(ip->jb, saved_jb, sizeof(jmp_buf));
        memcpy(ip->errmsg, saved_msg, sizeof(saved_msg));
        arena_free(&arena);
        ip->arena = outer;
        return;
    }
    eval_command(ip, action);
    memcpy(ip->jb, saved_jb, sizeof(jmp_buf));
    arena_free(&arena);
    ip->arena = outer;
}

/* --------------------------------------------------------------- dispatch */
Value *eval_command(Interp *ip, Node *node) {
    const char *name = node->text;
    Value **pos;
    int npos, nkws;
    Kwarg *kws;
    if (!strcmp(name, "draw"))
        return do_draw(ip, node);
    if (!strcmp(name, "draw_gui"))
        return do_draw_gui(ip, node);
    if (!strcmp(name, "draw_gui.button"))
        return do_gui_button(ip, node);
    if (!strcmp(name, "draw_gui.window_size"))
        return do_gui_window_size(ip, node);
    if (!strcmp(name, "python"))
        fail_at(ip, node->line, node->col,
                "python() was removed in 1.0.0 -- this build has no Python");
    if (!is_command(name)) {
        if (is_element(name))
            fail_at(ip, node->line, node->col,
                    "%s() only belongs inside draw() or draw_gui()", name);
        if (!strncmp(name, "draw_gui.", 9))
            fail_at(ip, node->line, node->col,
                    "draw_gui has no '.%.100s' -- it has .button and .window_size",
                    name + 9);
        fail_at(ip, node->line, node->col,
                "there is no command called %.100s -- OmniScript has draw, draw_gui, "
                "cmd, file, input, draw_gui.button, draw_gui.window_size", name);
    }
    call_args(ip, node, &pos, &npos, &kws, &nkws);
    if (!strcmp(name, "cmd"))
        return do_cmd(ip, node, pos, npos, nkws);
    if (!strcmp(name, "file"))
        return do_file(ip, node, pos, npos, nkws);
    return do_input(ip, node, pos, npos, kws, nkws);
}

static void eval_statement(Interp *ip, Node *node) {
    if (node->kind == ND_IMPORT || node->kind == ND_FROMIMPORT)
        fail_at(ip, node->line, node->col,
                "imports were removed in 1.0.0 -- this build has no Python");
    eval_command(ip, node);
}

int run_source(Interp *ip, const char *src, const char *name) {
    Arena arena;
    char err[512];
    int eline, ecol, nst, i;
    Token *toks;
    Node **sts;
    ip->source = (char *)src;
    if ((unsigned char)ip->source[0] == 0xef &&
        (unsigned char)ip->source[1] == 0xbb &&
        (unsigned char)ip->source[2] == 0xbf)
        ip->source += 3;       /* a byte-order mark is silently accepted */
    ip->name = (char *)name;
    arena_init(&arena);
    ip->arena = &arena;
    if (setjmp(ip->jb)) {
        char linebuf[512];
        int j, col = ip->errcol > 0 ? ip->errcol - 1 : 0;
        fprintf(stderr, "%s:%d: %s\n", name, ip->errline, ip->errmsg);
        if (line_text(ip->source, ip->errline, linebuf, sizeof(linebuf))[0]) {
            fprintf(stderr, "    %s\n    ", linebuf);
            for (j = 0; j < col; j++)
                fputc(' ', stderr);
            fprintf(stderr, "^\n");
        }
        arena_free(&arena);
        return 1;
    }
    toks = tokenize(&arena, ip->source, &eline, &ecol, err);
    if (!toks)
        fail_at(ip, eline, ecol, "%s", err);
    sts = parse_program(&arena, toks, ip->source, name, &nst, err, &eline, &ecol);
    if (!sts)
        fail_at(ip, eline, ecol, "%s", err);
    for (i = 0; i < nst; i++)
        eval_statement(ip, sts[i]);
    arena_free(&arena);
    return 0;
}
