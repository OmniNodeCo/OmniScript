#include "omni.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

typedef struct {
    Token *toks;
    int idx;
    Arena *a;
    const char *src, *name;
    char *err;
    int *eline, *ecol;
} Parser;

static Token *peek(Parser *p){ return &p->toks[p->idx]; }
static Token *peek2(Parser *p){ return &p->toks[p->idx+1]; }
static Token *take(Parser *p){ return &p->toks[p->idx++]; }
static int failed(Parser *p){ return p->err[0]!='\0'; }
static Node *fail(Parser *p, const char *msg, Token *t){
    if(!failed(p)){ snprintf(p->err,512,"%s",msg); *p->eline=t->line; *p->ecol=t->col; }
    return NULL;
}
static Node *new_node(Parser *p, NodeKind kind, int line, int col){
    Node *n=arena_alloc(p->a,sizeof(Node)); memset(n,0,sizeof(Node)); n->kind=kind; n->line=line; n->col=col; return n;
}
static void node_add_arg(Parser *p, Node *n, Node *arg){
    int cap=0,i; Node **na;
    cap=4; while(cap<=n->nargs) cap*=2;
    na=arena_alloc(p->a,sizeof(Node*)*(size_t)cap);
    for(i=0;i<n->nargs;i++) na[i]=n->args[i];
    n->args=na; n->args[n->nargs++]=arg;
}
static void node_add_kwarg(Parser *p, Node *n, Node *kw){
    int cap=0,i; Node **na;
    cap=4; while(cap<=n->nkwargs) cap*=2;
    na=arena_alloc(p->a,sizeof(Node*)*(size_t)cap);
    for(i=0;i<n->nkwargs;i++) na[i]=n->kwargs[i];
    n->kwargs=na; n->kwargs[n->nkwargs++]=kw;
}

/* forward */
static Node *parse_expr(Parser *p);
static Node *parse_atom(Parser *p);

/* dotted name: a.b.c as string */
static char *parse_dotted_name(Parser *p, int *line, int *col){
    Token *t=peek(p);
    if(t->kind!=TOK_NAME) return NULL;
    char *buf=arena_alloc(p->a,256); size_t len=0; int first=1;
    *line=t->line; *col=t->col;
    while(1){
        Token *name=peek(p);
        if(name->kind!=TOK_NAME) break;
        if(!first){ if(len+1>=256) break; buf[len++]='.'; }
        size_t nl=strlen(name->text);
        if(len+nl>=255) break;
        memcpy(buf+len,name->text,nl); len+=nl;
        take(p); first=0;
        if(peek(p)->kind==TOK_DOT){ take(p); continue; }
        break;
    }
    buf[len]='\0';
    char *out=arena_dup(p->a,buf);
    return out;
}

static Node *parse_import_stmt(Parser *p){
    Token *kw=take(p); // import
    Node *n=new_node(p,ND_IMPORT,kw->line,kw->col);
    ImportItem *items=NULL; int len=0,cap=0;
    while(1){
        int l,c; char *mod=parse_dotted_name(p,&l,&c);
        if(!mod){ fail(p,"expected module name after import",peek(p)); return NULL; }
        char *alias=NULL;
        if(peek(p)->kind==TOK_NAME && strcmp(peek(p)->text,"as")==0){
            take(p);
            Token *a=peek(p);
            if(a->kind!=TOK_NAME){ fail(p,"expected name after 'as'",a); return NULL; }
            alias=a->text; take(p);
        } else {
            // default alias = first component or full? Use full for simplicity, but for dotted use first part? We'll use last part? Let's use full for simplicity, but also first for compatibility.
            // We'll set alias to mod's last component
            char *dot=strrchr(mod,'.');
            alias= dot? dot+1 : mod;
        }
        if(len==cap){ cap=cap?cap*2:4; ImportItem *ni=arena_alloc(p->a,sizeof(ImportItem)*(size_t)cap); int i; for(i=0;i<len;i++) ni[i]=items[i]; items=ni; }
        items[len].name=mod; items[len].alias=alias; len++;
        if(peek(p)->kind==TOK_COMMA){ take(p); continue; }
        break;
    }
    n->imports=items; n->nimports=len;
    return n;
}

static Node *parse_from_import_stmt(Parser *p){
    Token *kw=take(p); // from
    int l,c; char *base=parse_dotted_name(p,&l,&c);
    if(!base){ fail(p,"expected module after 'from'",peek(p)); return NULL; }
    Token *imp=peek(p);
    if(imp->kind!=TOK_NAME || strcmp(imp->text,"import")!=0){ fail(p,"expected 'import' after 'from <module>'",imp); return NULL; }
    take(p);
    Node *n=new_node(p,ND_FROM_IMPORT,kw->line,kw->col);
    n->from_base=base;
    ImportItem *items=NULL; int len=0,cap=0;
    int paren=0;
    if(peek(p)->kind==TOK_LPAREN){ take(p); paren=1; }
    // handle *
    if(peek(p)->kind==TOK_STAR){
        Token *s=take(p);
        if(len==cap){ cap=4; items=arena_alloc(p->a,sizeof(ImportItem)*(size_t)cap); }
        items[0].name="*"; items[0].alias="*"; len=1;
        (void)s;
    } else {
        while(1){
            if(peek(p)->kind==TOK_RPAREN||peek(p)->kind==TOK_EOF||peek(p)->kind==TOK_NEWLINE) break;
            char *name=NULL; char *alias=NULL;
            Token *t=peek(p);
            if(t->kind!=TOK_NAME){ fail(p,"expected name to import",t); return NULL; }
            name=t->text; take(p);
            if(peek(p)->kind==TOK_NAME && strcmp(peek(p)->text,"as")==0){
                take(p);
                Token *a=peek(p);
                if(a->kind!=TOK_NAME){ fail(p,"expected name after 'as'",a); return NULL; }
                alias=a->text; take(p);
            } else alias=name;
            if(len==cap){ cap=cap?cap*2:4; ImportItem *ni=arena_alloc(p->a,sizeof(ImportItem)*(size_t)cap); int i; for(i=0;i<len;i++) ni[i]=items[i]; items=ni; }
            items[len].name=name; items[len].alias=alias; len++;
            if(peek(p)->kind==TOK_COMMA){ take(p); if(paren && peek(p)->kind==TOK_RPAREN) break; continue; }
            break;
        }
    }
    if(paren){
        if(peek(p)->kind!=TOK_RPAREN){ fail(p,"'(' after import is never closed",peek(p)); return NULL; }
        take(p);
    }
    n->imports=items; n->nimports=len;
    return n;
}

static Node *parse_arg(Parser *p){
    // check for NAME = expr
    Token *t=peek(p);
    if(t->kind==TOK_NAME && peek2(p)->kind==TOK_EQUAL){
        Token *key=take(p); take(p); // =
        Node *val=parse_expr(p);
        if(!val) return NULL;
        Node *kw=new_node(p,ND_KWARG,key->line,key->col);
        kw->text=key->text;
        kw->child=val;
        return kw;
    }
    return parse_expr(p);
}

static Node *parse_call_trail(Parser *p, Node *func){
    // func already, now '(' ... ')'
    Token *lp=take(p); // '('
    Node *call=new_node(p,ND_CALL,func->line,func->col);
    call->child=func;
    // skip newlines inside
    while(peek(p)->kind==TOK_NEWLINE) take(p);
    if(peek(p)->kind!=TOK_RPAREN){
        while(1){
            while(peek(p)->kind==TOK_NEWLINE) take(p);
            if(peek(p)->kind==TOK_RPAREN) break;
            Node *a=parse_arg(p);
            if(!a) return NULL;
            if(a->kind==ND_KWARG) node_add_kwarg(p,call,a);
            else node_add_arg(p,call,a);
            while(peek(p)->kind==TOK_NEWLINE) take(p);
            if(peek(p)->kind==TOK_COMMA){ take(p); continue; }
            break;
        }
    }
    while(peek(p)->kind==TOK_NEWLINE) take(p);
    if(peek(p)->kind!=TOK_RPAREN){ fail(p,"'(' is never closed",lp); return NULL; }
    take(p);
    return call;
}

static Node *parse_atom(Parser *p){
    Token *t=peek(p);
    if(t->kind==TOK_NUMBER){
        take(p);
        Node *n=new_node(p,ND_NUM,t->line,t->col);
        n->num=t->num; n->is_int=t->is_int; return n;
    }
    if(t->kind==TOK_STRING){
        take(p);
        Node *n=new_node(p,ND_STR,t->line,t->col);
        n->text=t->text; return n;
    }
    if(t->kind==TOK_NAME){
        take(p);
        Node *n=new_node(p,ND_NAME,t->line,t->col);
        n->text=t->text; return n;
    }
    if(t->kind==TOK_LPAREN){
        Token *lp=take(p);
        while(peek(p)->kind==TOK_NEWLINE) take(p);
        if(peek(p)->kind==TOK_RPAREN){
            take(p);
            Node *n=new_node(p,ND_TUPLE,lp->line,lp->col);
            return n;
        }
        Node *first=parse_expr(p);
        if(!first) return NULL;
        while(peek(p)->kind==TOK_NEWLINE) take(p);
        if(peek(p)->kind==TOK_COMMA){
            // tuple
            Node *tup=new_node(p,ND_TUPLE,lp->line,lp->col);
            node_add_arg(p,tup,first);
            while(peek(p)->kind==TOK_COMMA){
                take(p);
                while(peek(p)->kind==TOK_NEWLINE) take(p);
                if(peek(p)->kind==TOK_RPAREN) break;
                Node *el=parse_expr(p);
                if(!el) return NULL;
                node_add_arg(p,tup,el);
                while(peek(p)->kind==TOK_NEWLINE) take(p);
            }
            if(peek(p)->kind!=TOK_RPAREN){ fail(p,"'(' is never closed",lp); return NULL; }
            take(p);
            return tup;
        } else {
            if(peek(p)->kind!=TOK_RPAREN){ fail(p,"'(' is never closed",lp); return NULL; }
            take(p);
            return first;
        }
    }
    return fail(p,"expected a value",t);
}

static Node *parse_expr(Parser *p){
    Node *node=parse_atom(p);
    if(!node) return NULL;
    while(1){
        Token *t=peek(p);
        if(t->kind==TOK_DOT){
            take(p);
            Token *name=peek(p);
            if(name->kind!=TOK_NAME){ fail(p,"expected name after '.'",name); return NULL; }
            take(p);
            Node *attr=new_node(p,ND_ATTR,name->line,name->col);
            attr->child=node;
            attr->text=name->text;
            node=attr;
        } else if(t->kind==TOK_LPAREN){
            node=parse_call_trail(p,node);
            if(!node) return NULL;
        } else break;
    }
    return node;
}

static Node *parse_statement(Parser *p){
    while(peek(p)->kind==TOK_NEWLINE) take(p);
    Token *t=peek(p);
    if(t->kind==TOK_EOF) return NULL;
    if(t->kind==TOK_NAME && strcmp(t->text,"import")==0){
        return parse_import_stmt(p);
    }
    if(t->kind==TOK_NAME && strcmp(t->text,"from")==0){
        return parse_from_import_stmt(p);
    }
    // assignment? NAME = expr
    if(t->kind==TOK_NAME && peek2(p)->kind==TOK_EQUAL){
        Token *name=take(p); take(p);
        Node *val=parse_expr(p);
        if(!val) return NULL;
        Node *as=new_node(p,ND_ASSIGN,name->line,name->col);
        as->text=name->text;
        as->child=val;
        return as;
    }
    // expr stmt
    Node *e=parse_expr(p);
    if(!e) return NULL;
    Node *st=new_node(p,ND_EXPR_STMT,e->line,e->col);
    st->child=e;
    return st;
}

Node **parse_program(Arena *a, Token *toks, const char *src, const char *name, int *nstatements, char *err, int *eline, int *ecol){
    Parser p; p.toks=toks; p.idx=0; p.a=a; p.src=src; p.name=name; p.err=err; p.eline=eline; p.ecol=ecol;
    err[0]='\0';
    Node **out=NULL; int len=0,cap=0;
    while(1){
        while(peek(&p)->kind==TOK_NEWLINE) take(&p);
        if(peek(&p)->kind==TOK_EOF) break;
        Node *st=parse_statement(&p);
        if(!st) return NULL;
        if(len==cap){ cap=cap?cap*2:16; Node **no=arena_alloc(a,sizeof(Node*)*(size_t)cap); int i; for(i=0;i<len;i++) no[i]=out[i]; out=no; }
        out[len++]=st;
        // expect newline or EOF
        while(peek(&p)->kind==TOK_NEWLINE) take(&p);
    }
    *nstatements=len;
    return out;
}
