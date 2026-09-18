/* The front door: scripts, one-liners, the prompt, and updates. */
#include "omni.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <direct.h>
#define getcwd _getcwd
#else
#include <unistd.h>
#endif

static void usage(FILE *f) {
    fprintf(f,
            "OmniScript %s -- draw windows, run commands, handle files\n"
            "\n"
            "  omni FILE         run a script\n"
            "  omni -e CODE      run one line of code\n"
            "  omni update ...   fetch a newer OmniScript "
            "(try 'omni update --check')\n"
            "  omni --version    print the version\n"
            "  omni --help       this text\n"
            "  omni              open the interactive prompt\n",
            OMNI_VERSION);
}

static char *read_script(const char *path) {
    FILE *f = fopen(path, "rb");
    char *buf;
    size_t cap = 8192, len = 0, n;
    if (!f)
        return NULL;
    buf = malloc(cap);
    if (!buf) {
        fclose(f);
        return NULL;
    }
    for (;;) {
        if (len + 1024 > cap) {
            char *bigger = realloc(buf, cap * 2);
            if (!bigger) {
                free(buf);
                fclose(f);
                return NULL;
            }
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

static int run_file(Interp *ip, const char *path) {
    char *src = read_script(path);
    int rc;
    if (!src) {
        fprintf(stderr, "omni: cannot read %s: %s\n", path, strerror(errno));
        return 1;
    }
    rc = run_source(ip, src, path);
    free(src);
    return rc;
}

/* Split a REPL line the way a shell would (quotes, backslashes). */
static int split_line(char *line, char **argv, int cap) {
    int n = 0;
    char *p = line;
    while (*p) {
        char *w, quote = 0;
        while (*p == ' ' || *p == '\t')
            p++;
        if (!*p)
            break;
        if (n == cap)
            return -1;
        argv[n++] = p;
        w = p;
        while (*p && (quote || (*p != ' ' && *p != '\t'))) {
            if (quote && *p == quote) {
                quote = 0;
                p++;
            } else if (!quote && (*p == '"' || *p == '\'')) {
                quote = *p++;
            } else if (*p == '\\' && p[1]) {
                p++;
                *w++ = *p++;
            } else {
                *w++ = *p++;
            }
        }
        if (*p)
            p++;
        *w = '\0';
    }
    return n;
}

static void repl_help(void) {
    printf("Type OmniScript lines and they run.\n"
           "  help            this text\n"
           "  omni FILE       run a script without leaving\n"
           "  omni -e CODE    run one line without leaving\n"
           "  update ...      fetch a newer OmniScript\n"
           "  exit            leave the prompt\n"
           "\n"
           "The language:\n"
           "  draw(...)                     a window, or a BMP file\n"
           "  draw_gui(...)                 buttons that stay clickable\n"
           "  draw_gui.window_size(800, 600)\n"
           "  draw_gui.button(\"Go\", action=cmd(\"ls\"))\n"
           "  cmd(\"...\")                    run a shell command\n"
           "  file(create, \"a.txt\", \"hi\")\n"
           "  input(\"Name: \")               ask the person running it\n");
}

/* An `omni ...` line inside the prompt: same flags, same session. */
static void repl_omni(Interp *ip, char *rest) {
    char *argv[64];
    int n = split_line(rest, argv, 64);
    if (n < 0) {
        printf("omni: too many arguments\n");
        return;
    }
    if (n == 0) {
        usage(stdout);
        return;
    }
    if (strcmp(argv[0], "--version") == 0 || strcmp(argv[0], "-V") == 0) {
        printf("%s\n", OMNI_VERSION);
    } else if (strcmp(argv[0], "--help") == 0 || strcmp(argv[0], "-h") == 0) {
        usage(stdout);
    } else if (strcmp(argv[0], "update") == 0) {
        char *uargv[64];
        int i;
        uargv[0] = "update";
        for (i = 1; i < n; i++)
            uargv[i] = argv[i];
        update_main(n, uargv);
    } else if (strcmp(argv[0], "-e") == 0) {
        if (n < 2)
            printf("omni: -e needs code to run\n");
        else if (n > 2)
            printf("omni: unexpected argument '%s'\n", argv[2]);
        else
            run_source(ip, argv[1], "-e");
    } else if (argv[0][0] == '-') {
        printf("omni: unknown option '%s'\n", argv[0]);
    } else if (n > 1) {
        printf("omni: unexpected argument '%s'\n", argv[1]);
    } else {
        run_file(ip, argv[0]);
    }
}

/* A statement is finished when its parens balance outside of strings and it
 * holds no open triple-quoted string.
 */
static void scan_state(const char *line, int *parens, int *triple) {
    const char *p = line;
    int str = 0;
    while (*p && *p != '\n') {
        if (*triple) {
            if (p[0] == '"' && p[1] == '"' && p[2] == '"') {
                *triple = 0;
                p += 3;
            } else {
                p++;
            }
        } else if (str) {
            if (*p == '\\' && p[1]) {
                p += 2;
            } else if (*p == '"') {
                str = 0;
                p++;
            } else {
                p++;
            }
        } else if (*p == '#') {
            break;
        } else if (p[0] == '"' && p[1] == '"' && p[2] == '"') {
            *triple = 1;
            p += 3;
        } else if (*p == '"') {
            str = 1;
            p++;
        } else if (*p == '(') {
            (*parens)++;
            p++;
        } else if (*p == ')') {
            (*parens)--;
            p++;
        } else {
            p++;
        }
    }
}

static int repl(Interp *ip) {
    char *acc = NULL;
    size_t acap = 0, alen = 0;
    int parens = 0, triple = 0;
    printf("OmniScript %s -- type help, or exit to leave\n", OMNI_VERSION);
    for (;;) {
        char line[4096];
        char *cmd;
        fputs(alen ? ".... " : "omni> ", stdout);
        fflush(stdout);
        if (!fgets(line, sizeof(line), stdin)) {
            putchar('\n');
            break;
        }
        {
            size_t n = strlen(line);
            if (alen + n + 1 > acap) {
                size_t ncap = acap ? acap * 2 : 4096;
                char *bigger;
                while (ncap < alen + n + 1)
                    ncap *= 2;
                bigger = realloc(acc, ncap);
                if (!bigger) {
                    fprintf(stderr, "omni: out of memory\n");
                    free(acc);
                    return 1;
                }
                acc = bigger;
                acap = ncap;
            }
            memcpy(acc + alen, line, n + 1);
            alen += n;
        }
        scan_state(line, &parens, &triple);
        if (triple || parens > 0)
            continue;
        cmd = acc;
        while (*cmd == ' ' || *cmd == '\t' || *cmd == '\n')
            cmd++;
        {
            size_t n = strlen(cmd);
            while (n && (cmd[n - 1] == '\n' || cmd[n - 1] == ' ' ||
                         cmd[n - 1] == '\t'))
                cmd[--n] = '\0';
        }
        if (!*cmd) {
            goto reset;
        } else if (strcmp(cmd, "exit") == 0 || strcmp(cmd, "quit") == 0) {
            break;
        } else if (strcmp(cmd, "help") == 0) {
            repl_help();
        } else if (strcmp(cmd, "update") == 0 ||
                   strncmp(cmd, "update ", 7) == 0 ||
                   strncmp(cmd, "update\t", 7) == 0) {
            char *argv[64];
            char *uargv[64];
            int n = split_line(cmd, argv, 64), i;
            if (n < 0) {
                printf("omni: too many arguments\n");
            } else {
                for (i = 0; i < n; i++)
                    uargv[i] = argv[i];
                update_main(n, uargv);
            }
        } else if (strcmp(cmd, "omni") == 0 || strncmp(cmd, "omni ", 5) == 0 ||
                   strncmp(cmd, "omni\t", 5) == 0) {
            repl_omni(ip, cmd + 4);
        } else {
            run_source(ip, acc, "<repl>");
        }
reset:
        alen = 0;
        parens = 0;
        triple = 0;
        if (acc)
            acc[0] = '\0';
    }
    free(acc);
    return 0;
}

int main(int argc, char **argv) {
    Interp ip;
    char cwd[4096];
    int rc;
    if (!getcwd(cwd, sizeof(cwd)))
        strcpy(cwd, ".");
    interp_init(&ip, stdout, cwd);
    if (argc < 2) {
        rc = repl(&ip);
    } else if (strcmp(argv[1], "--version") == 0 ||
               strcmp(argv[1], "-V") == 0) {
        printf("%s\n", OMNI_VERSION);
        rc = 0;
    } else if (strcmp(argv[1], "--help") == 0 || strcmp(argv[1], "-h") == 0) {
        usage(stdout);
        rc = 0;
    } else if (strcmp(argv[1], "update") == 0) {
        rc = update_main(argc - 1, argv + 1);
    } else if (strcmp(argv[1], "-e") == 0) {
        if (argc < 3) {
            fprintf(stderr, "omni: -e needs code to run\n");
            rc = 2;
        } else if (argc > 3) {
            fprintf(stderr, "omni: unexpected argument '%s'\n", argv[3]);
            rc = 2;
        } else {
            rc = run_source(&ip, argv[2], "-e");
        }
    } else if (argv[1][0] == '-') {
        fprintf(stderr, "omni: unknown option '%s'\n", argv[1]);
        usage(stderr);
        rc = 2;
    } else if (argc > 2) {
        fprintf(stderr, "omni: unexpected argument '%s'\n", argv[2]);
        rc = 2;
    } else {
        rc = run_file(&ip, argv[1]);
    }
    interp_free(&ip);
    return rc;
}
