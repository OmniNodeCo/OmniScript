#include "omni.h"
#include <ctype.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    Token *toks;
    int len, cap;
    Arena *a;
} Lexer;

static void emit(Lexer *lx, TokKind kind, char *text, double num, int is_int, int line, int col){
    Token *t;
    if(lx->len==lx->cap){
        int ncap=lx->cap?lx->cap*2:64;
        Token *nt=arena_alloc(lx->a,sizeof(Token)*(size_t)ncap);
        if(lx->toks) memcpy(nt,lx->toks,sizeof(Token)*(size_t)lx->len);
        lx->toks=nt; lx->cap=ncap;
    }
    t=&lx->toks[lx->len++];
    t->kind=kind; t->text=text; t->num=num; t->is_int=is_int; t->line=line; t->col=col;
}

static int is_name_start(char c){ return c=='_'|| (c>='A'&&c<='Z')|| (c>='a'&&c<='z'); }
static int is_name_char(char c){ return is_name_start(c)|| (c>='0'&&c<='9'); }

static size_t number_len(const char *p){
    const char *q=p;
    if(*q=='-') q++;
    if(*q=='.') return (q[1]>='0'&&q[1]<='9')? 2+strspn(q+2,"0123456789"):0;
    if(*q<'0'||*q>'9') return 0;
    q+=strspn(q,"0123456789");
    if(*q=='.') q+=1+strspn(q+1,"0123456789");
    return (size_t)(q-p);
}

static char unesc(char c){
    switch(c){ case 'n':return '\n'; case 't':return '\t'; case 'r':return '\r'; case '"':return '"'; case '\'':return '\''; case '\\':return '\\'; case '0':return '\0'; default:return c; }
}

Token *tokenize(Arena *a, const char *src, char *err, int *eline, int *ecol){
    Lexer lx; const char *p=src; int line=1,col=1;
    lx.toks=NULL; lx.len=0; lx.cap=0; lx.a=a;
    *eline=0; *ecol=0; err[0]='\0';
    while(*p){
        if(*p==' '||*p=='\t'||*p=='\r'||*p=='\f'||*p=='\v'){ p++; col++; }
        else if(*p=='\n'){ emit(&lx,TOK_NEWLINE,arena_dup(a,"\\n"),0,0,line,col); p++; line++; col=1; }
        else if(*p=='#'){ while(*p&&*p!='\n'){p++; col++;} }
        else if(*p=='"'||*p=='\''){
            int tline=line,tcol=col; char quote=*p; const char *q=p+1; char *out,*w;
            out=arena_alloc(a,strlen(p)+1); w=out;
            for(;;){
                if(!*q||*q=='\n'){ *eline=tline; *ecol=tcol; snprintf(err,512,"string has no closing %c",quote); return NULL; }
                if(*q==quote){ q++; break; }
                if(*q=='\\'&&q[1]){ *w++=unesc(q[1]); if(q[1]=='\n'){line++; col=1;} else col+=2; q+=2; continue; }
                if(*q=='\n'){ line++; col=1; } else col++;
                *w++=*q++;
            }
            *w='\0'; col++; // closing quote
            emit(&lx,TOK_STRING,out,0,0,tline,tcol);
            p=q;
        } else if(is_name_start(*p)){
            const char *q=p; int tcol=col;
            while(is_name_char(*q)) {q++; col++;}
            emit(&lx,TOK_NAME,arena_dupn(a,p,(size_t)(q-p)),0,0,line,tcol);
            p=q;
        } else {
            size_t n=0;
            if((*p>='0'&&*p<='9')||*p=='.'||*p=='-') n=number_len(p);
            if(n){
                char *sp=arena_dupn(a,p,n); int tcol=col;
                emit(&lx,TOK_NUMBER,sp,strtod(sp,NULL), strchr(sp,'.')==NULL, line,tcol);
                p+=n; col+=(int)n;
            } else if(*p=='('){ emit(&lx,TOK_LPAREN,arena_dup(a,"("),0,0,line,col); p++; col++; }
            else if(*p==')'){ emit(&lx,TOK_RPAREN,arena_dup(a,")"),0,0,line,col); p++; col++; }
            else if(*p==','){ emit(&lx,TOK_COMMA,arena_dup(a,","),0,0,line,col); p++; col++; }
            else if(*p=='.'){ emit(&lx,TOK_DOT,arena_dup(a,"."),0,0,line,col); p++; col++; }
            else if(*p=='='){ emit(&lx,TOK_EQUAL,arena_dup(a,"="),0,0,line,col); p++; col++; }
            else if(*p=='*'){ emit(&lx,TOK_STAR,arena_dup(a,"*"),0,0,line,col); p++; col++; }
            else if(*p==':'){ emit(&lx,TOK_COLON,arena_dup(a,":"),0,0,line,col); p++; col++; }
            else if(*p==';'){ emit(&lx,TOK_NEWLINE,arena_dup(a,";"),0,0,line,col); p++; col++; }
            else { *eline=line; *ecol=col; snprintf(err,512,"cannot read '%c' here",*p); return NULL; }
        }
    }
    emit(&lx,TOK_EOF,arena_dup(a,""),0,0,line,col);
    return lx.toks;
}
