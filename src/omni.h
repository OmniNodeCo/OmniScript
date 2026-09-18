/* OmniScript native interpreter: shared types and helpers.
 *
 * One binary, libc only. No interpreter underneath, no libraries: the lexer,
 * parser, evaluator, pixel canvas, BMP writer, windows (X11 / Win32) and the
 * updater are all in this tree.
 */
#ifndef OMNI_H
#define OMNI_H

#include <setjmp.h>
#include <stddef.h>
#include <stdio.h>

#ifndef OMNI_VERSION
#define OMNI_VERSION "0.0.0"
#endif

/* ------------------------------------------------------------------ memory
 * Everything a statement builds (tokens, trees, values) lives in the line
 * arena and is dropped when the statement finishes -- or fails. Things that
 * outlive a statement (queued GUI buttons) use plain malloc and are freed
 * when cleared.
 */
typedef struct ArenaChunk {
    struct ArenaChunk *next;
    size_t len, cap;
    char data[];
} ArenaChunk;

typedef struct {
    ArenaChunk *head;
} Arena;

void arena_init(Arena *a);
void *arena_alloc(Arena *a, size_t n);
char *arena_dupn(Arena *a, const char *s, size_t n);
char *arena_dup(Arena *a, const char *s);
void arena_free(Arena *a);

/* ------------------------------------------------------------------- lexer
 * Token text for names/words points at owned copies; strings are unquoted.
 */
typedef enum {
    T_NUMBER, T_STRING, T_NAME, T_PUNCT, T_END
} TokKind;

typedef struct {
    TokKind kind;
    char *text;             /* number/name/punct spelling, or unquoted string */
    double num;
    int line, col;
} Token;

Token *tokenize(Arena *a, const char *src, int *eline, int *ecol,
                char *err /* 512 out */);

/* ------------------------------------------------------------------ parser */
typedef enum {
    ND_IMPORT, ND_FROMIMPORT, ND_CALL, ND_NUM, ND_STR, ND_WORD, ND_TUPLE, ND_KWARG
} NodeKind;

typedef struct {
    char *a, *b;            /* module, alias -- or name, alias */
} ImportItem;

typedef struct Node {
    NodeKind kind;
    char *text;             /* call/word name, string value, kwarg key */
    double num;
    int is_int;
    struct Node **args;
    int nargs;
    ImportItem *imports;    /* ND_IMPORT / ND_FROMIMPORT */
    int nimports;
    char *from_base;        /* ND_FROMIMPORT */
    int line, col;
} Node;

Node **parse_program(Arena *a, Token *toks, const char *src, const char *name,
                     int *nstatements /* out */,
                     char *err /* 512 out */, int *eline, int *ecol);

/* ------------------------------------------------------------------ values */
typedef enum { V_NUM, V_STR, V_WORD, V_TUPLE } ValueKind;

typedef struct Value {
    ValueKind kind;
    double num;
    int is_int;
    char *str;              /* V_STR, V_WORD */
    struct Value **items;   /* V_TUPLE */
    int nitems;
} Value;

/* ---------------------------------------------------------------- elements */
typedef enum {
    E_WINDOW, E_RECT, E_CIRCLE, E_LINE, E_TEXT, E_BUTTON, E_SAVE
} ElemKind;

#define E_SLOTS 8

typedef struct {
    ElemKind kind;
    Value *slot[E_SLOTS];   /* NULL means missing; see SLOTS in eval.c */
    Node *action;           /* a button's command, kept to run when clicked */
    int line;
} Element;

/* Element helpers shared by the evaluator and the GUI backends. */
struct Interp;
int elem_num(Value *v, int def, const char *what, int line, struct Interp *ip);
void elem_rgb(Value *v, int line, const char *def, unsigned char out[3],
              struct Interp *ip);
const char *elem_str(Value *v, const char *def, struct Interp *ip);
void gui_fire(struct Interp *ip, Node *action, const char *label);

/* ------------------------------------------------------------- interpreter */
typedef struct GuiButton {
    Element el;             /* deep copy; action tree also copied */
    struct GuiButton *next;
} GuiButton;

typedef struct Interp {
    char *source;           /* whole program text, for carets */
    char *name;             /* "<repl>", "-e", or a file */
    char cwd[4096];
    FILE *out;
    /* the GUI being built across statements */
    int gui_w, gui_h;
    char gui_title[256];
    char gui_bg[16];
    GuiButton *gui_buttons;
    /* errors longjmp back to the run boundary */
    jmp_buf jb;
    char errmsg[1024];
    int errline, errcol;
    Arena *arena;           /* the statement's arena */
} Interp;

void interp_init(Interp *ip, FILE *out, const char *cwd);
void interp_free(Interp *ip);          /* queued buttons */
void gui_clear(Interp *ip);

void say(Interp *ip, const char *msg);
void say_text(Interp *ip, const char *text);
void fail_at(Interp *ip, int line, int col, const char *fmt, ...);
const char *line_text(const char *src, int line, char *buf, size_t cap);

/* Run source; returns 0 or prints the error and returns 1. */
int run_source(Interp *ip, const char *src, const char *name);

/* One command node, evaluated (also used for button clicks). */
Value *eval_command(Interp *ip, Node *node);

/* Number formatting: integers print without ".0". */
void num_text(double num, int is_int, char *buf, size_t cap);

/* ------------------------------------------------------------------- canvas */
typedef struct {
    int w, h;
    unsigned char *px;      /* RGB, top-down */
} Canvas;

Canvas *canvas_new(int w, int h, const unsigned char bg[3]);
void canvas_free(Canvas *c);
void canvas_rect(Canvas *c, int x, int y, int w, int h, const unsigned char col[3]);
void canvas_outline(Canvas *c, int x, int y, int w, int h, const unsigned char col[3]);
void canvas_circle(Canvas *c, int cx, int cy, int r, const unsigned char col[3]);
void canvas_line(Canvas *c, int x1, int y1, int x2, int y2,
                 const unsigned char col[3], int width);
void canvas_text(Canvas *c, int x, int y, const char *msg,
                 const unsigned char col[3], int size);
int canvas_text_width(const char *msg, int size);
/* One dot of the built-in 5x7 font: 1 for ink, 0 for air. */
int font_pixel(char c, int col, int row);

/* 0 on success, -1 with errno set on failure. */
int img_write_bmp(const char *path, const Canvas *c);

/* ---------------------------------------------------------------------- gui
 * Returns 1 when a window was shown, 0 when this machine has none (the
 * caller then writes a file instead).
 */
int gui_available(void);
int gui_show(Interp *ip, Element *elems, int nelems, int w, int h,
             const char *title, const unsigned char bg[3]);

/* ------------------------------------------------------------------- update */
int update_main(int argc, char **argv);

/* Hex SHA-256 of a file; -1 when it cannot be read. */
int sha256_file(const char *path, char out[65]);

#endif
