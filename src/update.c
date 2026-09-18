/* The updater: new OmniScripts from GitHub releases. */
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
#else
#include <unistd.h>
#endif
#include <sys/stat.h>
#ifdef __APPLE__
#include <mach-o/dyld.h>
#endif

#define DEFAULT_REPO "OmniNodeCo/OmniScript"
#define API "https://api.github.com"

/* ------------------------------------------------------------------ JSON */
/* Just enough JSON for release objects: strings, booleans, and splitting an
 * array of objects. Strings understand \" \\ \n \t \r \uXXXX.
 */
static void append_utf8(char **w, char *end, unsigned cp) {
    if (cp < 0x80) {
        if (*w < end)
            *(*w)++ = (char)cp;
    } else if (cp < 0x800) {
        if (*w + 1 < end) {
            *(*w)++ = (char)(0xc0 | (cp >> 6));
            *(*w)++ = (char)(0x80 | (cp & 0x3f));
        }
    } else {
        if (*w + 2 < end) {
            *(*w)++ = (char)(0xe0 | (cp >> 12));
            *(*w)++ = (char)(0x80 | ((cp >> 6) & 0x3f));
            *(*w)++ = (char)(0x80 | (cp & 0x3f));
        }
    }
}

static int hex4(const char *p, unsigned *cp) {
    int i;
    unsigned v = 0;
    for (i = 0; i < 4; i++) {
        char c = p[i];
        v <<= 4;
        if (c >= '0' && c <= '9')
            v |= (unsigned)(c - '0');
        else if (c >= 'a' && c <= 'f')
            v |= (unsigned)(c - 'a' + 10);
        else if (c >= 'A' && c <= 'F')
            v |= (unsigned)(c - 'A' + 10);
        else
            return 0;
    }
    *cp = v;
    return 1;
}

/* Copies the string value of "key" (searched from obj) into out. */
static int json_string(const char *obj, const char *key, char *out, size_t cap) {
    char pat[64];
    const char *at, *p;
    char *w = out, *end = out + cap - 1;
    snprintf(pat, sizeof(pat), "\"%s\"", key);
    at = strstr(obj, pat);
    if (!at)
        return 0;
    p = strchr(at + strlen(pat), ':');
    if (!p)
        return 0;
    p++;
    while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r')
        p++;
    if (*p == 'n' && !strncmp(p, "null", 4)) {
        out[0] = '\0';
        return 1;
    }
    if (*p != '"')
        return 0;
    p++;
    while (*p && *p != '"') {
        if (*p == '\\') {
            char e = p[1];
            if (e == 'n' && w < end)
                *w++ = '\n';
            else if (e == 't' && w < end)
                *w++ = '\t';
            else if (e == 'r' && w < end)
                *w++ = '\r';
            else if ((e == '"' || e == '\\' || e == '/') && w < end)
                *w++ = e;
            else if (e == 'u') {
                unsigned cp;
                if (hex4(p + 2, &cp))
                    append_utf8(&w, end, cp);
                p += 4;
            } else if (w < end) {
                *w++ = e;
            }
            p += 2;
        } else {
            if (w < end)
                *w++ = *p;
            p++;
        }
    }
    *w = '\0';
    return *p == '"';
}

static int json_bool(const char *obj, const char *key, int *val) {
    char pat[64];
    const char *at, *p;
    snprintf(pat, sizeof(pat), "\"%s\"", key);
    at = strstr(obj, pat);
    if (!at)
        return 0;
    p = strchr(at + strlen(pat), ':');
    if (!p)
        return 0;
    p++;
    while (*p == ' ' || *p == '\t')
        p++;
    if (!strncmp(p, "true", 4)) {
        *val = 1;
        return 1;
    }
    if (!strncmp(p, "false", 5)) {
        *val = 0;
        return 1;
    }
    return 0;
}

/* Calls visit(start, len, ctx) for each top-level {...} inside an array. */
static void json_items(const char *arr,
                       void (*visit)(const char *, size_t, void *), void *ctx) {
    const char *p = arr;
    while (*p && *p != '[')
        p++;
    if (!*p)
        return;
    p++;
    for (;;) {
        const char *start;
        int depth = 0, instr = 0;
        while (*p && (*p != '{' || instr)) {
            if (*p == '"' && (p == arr || *(p - 1) != '\\'))
                instr = !instr;
            p++;
        }
        if (!*p)
            return;
        start = p;
        instr = 0;
        while (*p) {
            if (instr) {
                if (*p == '\\' && p[1])
                    p++;
                else if (*p == '"')
                    instr = 0;
            } else if (*p == '"') {
                instr = 1;
            } else if (*p == '{') {
                depth++;
            } else if (*p == '}') {
                depth--;
                if (!depth) {
                    p++;
                    break;
                }
            }
            p++;
        }
        visit(start, (size_t)(p - start), ctx);
        while (*p && *p != ',' && *p != ']')
            p++;
        if (*p != ',')
            return;
        p++;
    }
}

/* ------------------------------------------------------------------ HTTP */
static char *slurp(const char *path, size_t *len_out) {
    FILE *f = fopen(path, "rb");
    char *buf;
    size_t cap = 65536, len = 0, n;
    if (!f)
        return NULL;
    buf = malloc(cap);
    if (!buf) {
        fclose(f);
        return NULL;
    }
    for (;;) {
        if (len + 8192 > cap) {
            char *bigger = realloc(buf, cap * 2);
            if (!bigger) {
                free(buf);
                fclose(f);
                return NULL;
            }
            buf = bigger;
            cap *= 2;
        }
        n = fread(buf + len, 1, 8191, f);
        len += n;
        if (n < 8191)
            break;
    }
    buf[len] = '\0';
    fclose(f);
    if (len_out)
        *len_out = len;
    return buf;
}

/* GET a URL into a temp body file; returns the HTTP status (0 = curl itself
 * failed). The caller removes the body file.
 */
static long http_get(const char *url, const char *body_path, int timeout) {
    char cmd[4096], code[16];
    FILE *pp;
    long status = 0;
    snprintf(cmd, sizeof(cmd),
             "curl -sS --max-time %d -H \"Accept: application/vnd.github+json\" "
             "-o \"%s\" -w \"%%{http_code}\" \"%s\" 2>\"%s.err\"",
             timeout, body_path, url, body_path);
    pp = popen(cmd, "r");
    if (!pp)
        return 0;
    if (!fgets(code, sizeof(code), pp))
        code[0] = '\0';
    {
        int rc = pclose(pp);
#ifdef _WIN32
        if (rc != 0 && code[0] == '\0')
            return 0;
#else
        if (rc != 0 && code[0] == '\0')
            return 0;
#endif
    }
    status = strtol(code, NULL, 10);
    {
        char errpath[4096];
        snprintf(errpath, sizeof(errpath), "%s.err", body_path);
        remove(errpath);
    }
    return status;
}

static int http_download(const char *url, const char *dest) {
    char cmd[4096];
    int rc;
    FILE *pp;
    snprintf(cmd, sizeof(cmd), "curl -sS --max-time 600 -L -o \"%s\" \"%s\"",
             dest, url);
    pp = popen(cmd, "r");
    if (!pp)
        return -1;
    {
        char buf[256];
        while (fgets(buf, sizeof(buf), pp)) {
        }
    }
    rc = pclose(pp);
#ifdef _WIN32
    return rc == 0 ? 0 : -1;
#else
    return rc == 0 ? 0 : -1;
#endif
}

/* --------------------------------------------------------------- versions */
static int version_parts(const char *v, long *p1, long *p2, long *p3) {
    char *end;
    *p1 = strtol(v, &end, 10);
    if (end == v)
        return 0;
    *p2 = 0;
    *p3 = 0;
    if (*end == '.') {
        v = end + 1;
        *p2 = strtol(v, &end, 10);
        if (*end == '.') {
            v = end + 1;
            *p3 = strtol(v, &end, 10);
        }
    }
    return *end == '\0';
}

/* -1 / 0 / 1 comparing dotted versions. */
static int version_cmp(const char *a, const char *b) {
    long a1, a2, a3, b1, b2, b3;
    if (!version_parts(a, &a1, &a2, &a3))
        return -2;
    if (!version_parts(b, &b1, &b2, &b3))
        return 2;
    if (a1 != b1)
        return a1 < b1 ? -1 : 1;
    if (a2 != b2)
        return a2 < b2 ? -1 : 1;
    if (a3 != b3)
        return a3 < b3 ? -1 : 1;
    return 0;
}

static const char *version_from_tag(const char *tag) {
    if ((tag[0] == 'v' || tag[0] == 'V') && tag[1] >= '0' && tag[1] <= '9')
        return tag + 1;
    return tag;
}

/* ------------------------------------------------------------- the release */
typedef struct {
    char tag[64];
    char body[65536];
    int prerelease;
    char asset_url[1024];
    char hash_url[1024];
    char asset_names[2048];
} Release;

typedef struct {
    const char *want;
    Release *rel;
} AssetCtx;

static void asset_visit(const char *start, size_t len, void *ctx) {
    AssetCtx *ac = ctx;
    char *obj = malloc(len + 1);
    char name[256], url[1024];
    if (!obj)
        return;
    memcpy(obj, start, len);
    obj[len] = '\0';
    if (json_string(obj, "name", name, sizeof(name))) {
        size_t have = strlen(ac->rel->asset_names);
        if (have + strlen(name) + 3 < sizeof(ac->rel->asset_names)) {
            if (have)
                strcat(ac->rel->asset_names + have, ", ");
            strcat(ac->rel->asset_names + have, name);
        }
        if (strcmp(name, ac->want) == 0)
            json_string(obj, "browser_download_url", url, sizeof(url)) &&
                (snprintf(ac->rel->asset_url, sizeof(ac->rel->asset_url), "%s",
                          url),
                 1);
        {
            char hashname[300];
            snprintf(hashname, sizeof(hashname), "%s.sha256", ac->want);
            if (strcmp(name, hashname) == 0)
                json_string(obj, "browser_download_url", url, sizeof(url)) &&
                    (snprintf(ac->rel->hash_url, sizeof(ac->rel->hash_url),
                              "%s", url),
                     1);
        }
    }
    free(obj);
}

static void asset_name(char *out, size_t cap) {
    const char *os =
#ifdef _WIN32
        "windows";
#elif defined(__APPLE__)
        "macos";
#else
        "linux";
#endif
    const char *arch =
#if defined(__aarch64__) || defined(_M_ARM64)
        "arm64";
#elif defined(__i386__) || defined(_M_IX86)
        "x86";
#else
        "x86_64";
#endif
    snprintf(out, cap, "omni-%s-%s%s", os, arch,
#ifdef _WIN32
             ".exe"
#else
             ""
#endif
    );
}

static int parse_release(const char *body, const char *want, Release *rel) {
    const char *assets;
    AssetCtx ac;
    memset(rel, 0, sizeof(*rel));
    if (!json_string(body, "tag_name", rel->tag, sizeof(rel->tag)))
        return 0;
    json_bool(body, "prerelease", &rel->prerelease);
    json_string(body, "body", rel->body, sizeof(rel->body));
    assets = strstr(body, "\"assets\"");
    if (!assets)
        return 1;
    ac.want = want;
    ac.rel = rel;
    json_items(assets, asset_visit, &ac);
    return 1;
}

typedef struct {
    const char *tag;
    char *found;
} TagCtx;

static void tag_visit(const char *start, size_t len, void *ctx) {
    TagCtx *tc = ctx;
    char *obj;
    char tag[64];
    if (tc->found)
        return;
    obj = malloc(len + 1);
    if (!obj)
        return;
    memcpy(obj, start, len);
    obj[len] = '\0';
    if (json_string(obj, "tag_name", tag, sizeof(tag)) &&
        strcmp(tag, tc->tag) == 0) {
        tc->found = obj;
        return;
    }
    free(obj);
}

typedef struct {
    char *found;
} BetaCtx;

static void beta_visit(const char *start, size_t len, void *ctx) {
    BetaCtx *bc = ctx;
    char *obj;
    int pre = 0;
    if (bc->found)
        return;
    obj = malloc(len + 1);
    if (!obj)
        return;
    memcpy(obj, start, len);
    obj[len] = '\0';
    if (json_bool(obj, "prerelease", &pre) && pre) {
        bc->found = obj;
        return;
    }
    free(obj);
}

static void tmp_body(char *out, size_t cap) {
    const char *tmp =
#ifdef _WIN32
        getenv("TEMP");
#else
        "/tmp";
#endif
#ifdef _WIN32
    if (!tmp || strchr(tmp, '"'))
        tmp = ".";
#endif
    snprintf(out, cap, "%s/omni-update-%ld.json", tmp, (long)
#ifdef _WIN32
             GetCurrentProcessId()
#else
             getpid()
#endif
    );
}

/* Fetch the release JSON for the wanted version/channel. Returns 1 with *body
 * set, or 0 after printing why not.
 */
static int fetch_release(const char *repo, const char *version, int beta,
                         char **body) {
    char url[1024], path[1024];
    long st;
    tmp_body(path, sizeof(path));
    if (version) {
        snprintf(url, sizeof(url), API "/repos/%s/releases/tags/v%s", repo,
                 version);
        st = http_get(url, path, 60);
        if (st == 200) {
            *body = slurp(path, NULL);
            remove(path);
            if (*body)
                return 1;
            fprintf(stderr, "omni update: could not read GitHub's answer\n");
            return 0;
        }
        if (st == 404) {
            /* Tags are vX.Y.Z; also try the bare version, then the list. */
            char list[1024], lpath[1024];
            char *lbody;
            long lst;
            snprintf(list, sizeof(list), API "/repos/%s/releases?per_page=100",
                     repo);
            tmp_body(lpath, sizeof(lpath));
            lst = http_get(list, lpath, 60);
            remove(path);
            if (lst != 200) {
                remove(lpath);
                fprintf(stderr, "omni update: release %s not found\n", version);
                return 0;
            }
            lbody = slurp(lpath, NULL);
            remove(lpath);
            if (lbody) {
                TagCtx tc;
                char tag[64];
                snprintf(tag, sizeof(tag), "v%s", version);
                tc.tag = tag;
                tc.found = NULL;
                json_items(lbody, tag_visit, &tc);
                if (!tc.found) {
                    tc.tag = version;
     
                    json_items(lbody, tag_visit, &tc);
                }
                free(lbody);
                if (tc.found) {
                    *body = tc.found;
                    return 1;
                }
            }
            fprintf(stderr, "omni update: release %s not found\n", version);
            return 0;
        }
        remove(path);
        if (st == 0) {
            fprintf(stderr,
                    "omni update: could not reach GitHub -- is curl installed "
                    "and online?\n");
            return 0;
        }
        fprintf(stderr, "omni update: GitHub answered %ld\n", st);
        return 0;
    }
    if (!beta) {
        snprintf(url, sizeof(url), API "/repos/%s/releases/latest", repo);
        st = http_get(url, path, 60);
        if (st == 404) {
            remove(path);
            fprintf(stderr, "omni update: no stable release yet\n");
            return 0;
        }
    } else {
        snprintf(url, sizeof(url), API "/repos/%s/releases?per_page=20", repo);
        st = http_get(url, path, 60);
    }
    if (st == 0) {
        remove(path);
        fprintf(stderr,
                "omni update: could not reach GitHub -- is curl installed and "
                "online?\n");
        return 0;
    }
    if (st != 200) {
        remove(path);
        fprintf(stderr, "omni update: GitHub answered %ld\n", st);
        return 0;
    }
    {
        char *lbody = slurp(path, NULL);
        remove(path);
        if (!lbody) {
            fprintf(stderr, "omni update: could not read GitHub's answer\n");
            return 0;
        }
        if (!beta) {
            *body = lbody;
            return 1;
        }
        {
            BetaCtx bc;
            bc.found = NULL;
            json_items(lbody, beta_visit, &bc);
            free(lbody);
            if (!bc.found) {
                fprintf(stderr, "omni update: no beta release yet\n");
                return 0;
            }
            *body = bc.found;
            return 1;
        }
    }
}

/* Where the running OmniScript lives, for in-place updates. */
static int exe_path(char *out, size_t cap) {
#ifdef __APPLE__
    uint32_t size = (uint32_t)cap;
    if (_NSGetExecutablePath(out, &size) != 0)
        return 0;
    return 1;
#elif defined(_WIN32)
    return GetModuleFileNameA(NULL, out, (DWORD)cap) != 0;
#else
    ssize_t n = readlink("/proc/self/exe", out, cap - 1);
    if (n < 0)
        return 0;
    out[n] = '\0';
    return 1;
#endif
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

int update_main(int argc, char **argv) {
    int check = 0, i, npos = 0;
    const char *version = NULL, *channel = "stable", *target = NULL;
    const char *repo = DEFAULT_REPO;
    const char *pos[4];
    long a, b, c;
    char want[128], *body = NULL;
    Release rel;
    const char *release_version;
    int cmp;
    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--check") == 0) {
            check = 1;
        } else if (argv[i][0] == '-') {
            fprintf(stderr, "omni update: unknown option '%s'\n", argv[i]);
            return 2;
        } else if (npos < 4) {
            pos[npos++] = argv[i];
        } else {
            fprintf(stderr,
                    "omni update: too many arguments "
                    "(want [version] [channel] [target] [repo])\n");
            return 2;
        }
    }
    if (npos > 0)
        version = pos[0];
    if (npos > 1)
        channel = pos[1];
    if (npos > 2)
        target = pos[2];
    if (npos > 3)
        repo = pos[3];
    if (version && strcmp(version, "latest") != 0) {
        if (version[0] == 'v' || version[0] == 'V')
            version++;
        if (!version_parts(version, &a, &b, &c)) {
            fprintf(stderr, "omni update: '%s' is not a version like 1.2.0\n",
                    version);
            return 2;
        }
    } else {
        version = NULL;
    }
    {
        /* The repo reaches a shell command, so it must be boring. */
        size_t k, slash = 0;
        for (k = 0; repo[k]; k++) {
            char ch = repo[k];
            if (ch == '/')
                slash++;
            else if (!isalnum((unsigned char)ch) && ch != '.' && ch != '_' &&
                     ch != '-') {
                fprintf(stderr,
                        "omni update: '%s' is not a repo like owner/name\n",
                        repo);
                return 2;
            }
        }
        if (slash != 1 || repo[0] == '/' || repo[strlen(repo) - 1] == '/') {
            fprintf(stderr, "omni update: '%s' is not a repo like owner/name\n",
                    repo);
            return 2;
        }
    }
    if (strcmp(channel, "stable") != 0 && strcmp(channel, "beta") != 0) {
        fprintf(stderr, "omni update: channel is stable or beta, not '%s'\n",
                channel);
        return 2;
    }
    if (target) {
        struct stat st;
        char probe[4096];
        snprintf(probe, sizeof(probe), "%s", target);
        if (stat(probe, &st) != 0) {
            char mk[4096];
            snprintf(mk, sizeof(mk), "%s/x", target);
            make_parents(mk);
#ifdef _WIN32
            _mkdir(target);
#else
            mkdir(target, 0755);
#endif
        }
    }
    asset_name(want, sizeof(want));
    if (!fetch_release(repo, version, strcmp(channel, "beta") == 0, &body))
        return 1;
    if (!parse_release(body, want, &rel)) {
        fprintf(stderr, "omni update: GitHub's answer made no sense\n");
        free(body);
        return 1;
    }
    release_version = version_from_tag(rel.tag);
    cmp = version_cmp(OMNI_VERSION, release_version);
    if (check) {
        if (cmp >= 0)
            printf("OmniScript %s is the newest %s\n", OMNI_VERSION, channel);
        else
            printf("OmniScript %s is available (you have %s) -- run 'omni "
                   "update%s' to install it\n",
                   release_version, OMNI_VERSION,
                   strcmp(channel, "beta") == 0 ? " latest beta" : "");
        free(body);
        return 0;
    }
    if (!rel.asset_url[0]) {
        fprintf(stderr,
                "omni update: release %s has no file for this machine (%s)",
                rel.tag, want);
        if (rel.asset_names[0])
            fprintf(stderr, " -- it has: %s", rel.asset_names);
        fprintf(stderr, "\n");
        free(body);
        return 1;
    }
    if (cmp >= 0 && !version) {
        printf("OmniScript %s is the newest %s\n", OMNI_VERSION, channel);
        free(body);
        return 0;
    }
    {
        char tmp[1024], dest[4096], hashpath[1100], expected[128], actual[65];
        char *hashbody;
        size_t n;
        const char *exe;
        printf("downloading OmniScript %s (%s)...\n", release_version, want);
        fflush(stdout);
        tmp_body(tmp, sizeof(tmp));
        if (http_download(rel.asset_url, tmp) != 0) {
            fprintf(stderr, "omni update: the download failed\n");
            remove(tmp);
            free(body);
            return 1;
        }
        if (!rel.hash_url[0]) {
            fprintf(stderr,
                    "omni update: release %s publishes no checksum -- refusing "
                    "to install\n",
                    rel.tag);
            remove(tmp);
            free(body);
            return 1;
        }
        snprintf(hashpath, sizeof(hashpath), "%s.sha256", tmp);
        if (http_download(rel.hash_url, hashpath) != 0) {
            fprintf(stderr, "omni update: could not fetch the checksum\n");
            remove(tmp);
            free(body);
            return 1;
        }
        hashbody = slurp(hashpath, &n);
        remove(hashpath);
        if (!hashbody || sscanf(hashbody, "%127s", expected) != 1) {
            fprintf(stderr, "omni update: the checksum file made no sense\n");
            free(hashbody);
            remove(tmp);
            free(body);
            return 1;
        }
        free(hashbody);
        if (sha256_file(tmp, actual) != 0) {
            fprintf(stderr, "omni update: could not read the download\n");
            remove(tmp);
            free(body);
            return 1;
        }
        {
            size_t k;
            for (k = 0; expected[k]; k++)
                expected[k] = (char)tolower((unsigned char)expected[k]);
        }
        if (strcmp(expected, actual) != 0) {
            fprintf(stderr,
                    "omni update: the download does not match its checksum -- "
                    "deleted\n");
            remove(tmp);
            free(body);
            return 1;
        }
        if (target) {
            snprintf(dest, sizeof(dest), "%s/%s", target,
#ifdef _WIN32
                     "omni.exe"
#else
                     "omni"
#endif
            );
        } else {
            if (!exe_path(dest, sizeof(dest))) {
                fprintf(stderr,
                        "omni update: cannot find the running OmniScript -- "
                        "give a target folder\n");
                remove(tmp);
                free(body);
                return 1;
            }
        }
        exe = dest;
#ifndef _WIN32
        chmod(tmp, 0755);
#endif
        if (rename(tmp, dest) != 0) {
#ifdef _WIN32
            char alt[4096];
            snprintf(alt, sizeof(alt), "%s.new", dest);
            if (rename(tmp, alt) == 0) {
                printf("saved as %s -- close OmniScript, rename it over %s\n",
                       alt, dest);
                free(body);
                return 0;
            }
#endif
            fprintf(stderr, "omni update: could not write %s: %s\n", exe,
                    strerror(errno));
            remove(tmp);
            free(body);
            return 1;
        }
        printf("updated to OmniScript %s\n", release_version);
        if (rel.body[0])
            printf("\n%s\n", rel.body);
        free(body);
        return 0;
    }
}
