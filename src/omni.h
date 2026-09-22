/* OmniScript — super simple language
 * - imports like python
 * - draw module with gui buttons
 * - cmd module runs background commands
 * - pathlib module like python
 */
#ifndef OMNI_H
#define OMNI_H

#include <setjmp.h>
#include <stddef.h>
#include <stdio.h>

#ifndef OMNI_VERSION
#define OMNI_VERSION "1.0.2-simple"
#endif

/* ---------- arena */
typedef struct ArenaChunk {
    struct ArenaChunk *next;
    size_t len, cap;
    char data[];
} ArenaChunk;
typedef struct { ArenaChunk *head; } Arena;
void arena_init(Arena *a);
void *arena_alloc(Arena *a, size_t n);
char *arena_dupn(Arena *a, const char *s, size_t n);
char *arena_dup(Arena *a, const char *s);
void arena_free(Arena *a);

/* ---------- tokens */
typedef enum {
    TOK_EOF,
    TOK_NEWLINE,
    TOK_NUMBER,
    TOK_STRING,
    TOK_NAME,
    TOK_LPAREN,
    TOK_RPAREN,
    TOK_COMMA,
    TOK_DOT,
    TOK_EQUAL,
    TOK_STAR,
    TOK_COLON
} TokKind;

typedef struct {
    TokKind kind;
    char *text; /* owned by arena, unquoted for strings */
    double num;
    int is_int;
    int line, col;
} Token;

Token *tokenize(Arena *a, const char *src, char *err /*512*/, int *eline, int *ecol);

/* ---------- parser */
typedef struct {
    char *name;  /* module/name */
    char *alias; /* as */
} ImportItem;

typedef enum {
    ND_IMPORT,
    ND_FROM_IMPORT,
    ND_ASSIGN,
    ND_EXPR_STMT,
    ND_CALL,
    ND_ATTR,
    ND_NAME,
    ND_NUM,
    ND_STR,
    ND_TUPLE,
    ND_KWARG
} NodeKind;

typedef struct Node {
    NodeKind kind;
    char *text; /* name, string value, attr name, kwarg key, assign var */
    double num;
    int is_int;
    struct Node *child; /* for ATTR: object, for CALL: func, for ASSIGN: value, for EXPR_STMT: expr, for KWARG: value */
    struct Node **args; /* positional args for CALL, items for TUPLE */
    int nargs;
    struct Node **kwargs; /* for CALL: list of KWARG nodes */
    int nkwargs;
    ImportItem *imports;
    int nimports;
    char *from_base;
    int line, col;
} Node;

Node **parse_program(Arena *a, Token *toks, const char *src, const char *name,
                     int *nstatements, char *err, int *eline, int *ecol);

/* ---------- values */
typedef enum {
    V_NIL,
    V_NUM,
    V_STR,
    V_BOOL,
    V_TUPLE,
    V_MODULE,
    V_FUNC,
    V_PATH,
    V_ELEMENT
} ValueKind;

typedef struct Value Value;
typedef struct Kwarg {
    char *key;
    Value *val;
    int line, col;
} Kwarg;

typedef struct Interp Interp;
typedef Value* (*BuiltinFunc)(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line);

typedef struct Binding {
    char *name;
    Value *val;
    struct Binding *next;
} Binding;

typedef struct Env {
    Binding *head;
} Env;

struct Value {
    ValueKind kind;
    double num;
    int is_int;
    char *str; /* for STR, PATH */
    int boolean; /* for BOOL */
    Value **items;
    int nitems;
    /* module */
    Env *env;
    char *mod_name;
    BuiltinFunc mod_call;
    /* func */
    BuiltinFunc func;
    char *func_name;
    Value *bound; /* for bound methods */
    /* element */
    struct Element *elem;
};

/* ---------- draw elements */
typedef enum {
    E_WINDOW,
    E_RECT,
    E_CIRCLE,
    E_LINE,
    E_TEXT,
    E_BUTTON,
    E_SAVE
} ElemKind;

typedef struct Element {
    ElemKind kind;
    int x, y, w, h, r, x2, y2;
    unsigned char color[3];
    unsigned char bg[3]; /* for window bg */
    char *text; /* label, message, path, title */
    int size; /* text size, line width for line */
    char *action; /* for button: shell command string (malloced) */
    int line;
} Element;

/* ---------- interpreter */
struct Interp {
    char *source;
    char *name;
    char cwd[4096];
    FILE *out;
    Arena *arena;
    Env globals;
    Env modules; /* name -> module Value */
    /* draw state */
    int draw_w, draw_h;
    char draw_title[256];
    unsigned char draw_bg[3];
    Element *draw_elems;
    int draw_nelems;
    int draw_cap;
    /* error */
    jmp_buf jb;
    char errmsg[1024];
    int errline, errcol;
};

void interp_init(Interp *ip, FILE *out, const char *cwd);
void interp_free(Interp *ip);
void say(Interp *ip, const char *msg);
void say_text(Interp *ip, const char *text);
void fail_at(Interp *ip, int line, int col, const char *fmt, ...);
const char *line_text(const char *src, int line, char *buf, size_t cap);
void num_text(double num, int is_int, char *buf, size_t cap);

/* env */
void env_set(Env *e, const char *name, Value *v);
Value *env_get(Env *e, const char *name);
void env_set_heap(Env *e, const char *name, Value *v); /* malloced name */
int env_has(Env *e, const char *name);

/* value helpers */
Value *val_nil(Interp *ip);
Value *val_num(Interp *ip, double n, int is_int);
Value *val_str(Interp *ip, const char *s);
Value *val_bool(Interp *ip, int b);
Value *val_tuple(Interp *ip, Value **items, int n);
Value *val_module(Interp *ip, const char *name, BuiltinFunc call);
Value *val_func(Interp *ip, const char *name, BuiltinFunc fn);
Value *val_func_bound(Interp *ip, const char *name, BuiltinFunc fn, Value *bound);
Value *val_path(Interp *ip, const char *path);
Value *val_element(Interp *ip, Element *el);
const char *val_to_string(Interp *ip, Value *v); /* arena allocated */
int val_to_int(Value *v, int def);
double val_to_num(Value *v, double def);
int val_is_truthy(Value *v);

/* run */
int run_source(Interp *ip, const char *src, const char *name);
Value *eval_expr(Interp *ip, Node *node);

/* canvas */
typedef struct {
    int w, h;
    unsigned char *px;
} Canvas;
Canvas *canvas_new(int w, int h, const unsigned char bg[3]);
void canvas_free(Canvas *c);
void canvas_rect(Canvas *c, int x, int y, int w, int h, const unsigned char col[3]);
void canvas_outline(Canvas *c, int x, int y, int w, int h, const unsigned char col[3]);
void canvas_circle(Canvas *c, int cx, int cy, int r, const unsigned char col[3]);
void canvas_line(Canvas *c, int x1, int y1, int x2, int y2, const unsigned char col[3], int width);
void canvas_text(Canvas *c, int x, int y, const char *msg, const unsigned char col[3], int size);
int canvas_text_width(const char *msg, int size);
int font_pixel(char c, int col, int row);
int img_write_bmp(const char *path, const Canvas *c);

/* gui */
int gui_available(void);
int gui_show(Interp *ip, Element *elems, int nelems, int w, int h, const char *title, const unsigned char bg[3]);

/* modules init */
void modules_init(Interp *ip);

/* color */
int parse_color(const char *s, unsigned char out[3]);

#endif
