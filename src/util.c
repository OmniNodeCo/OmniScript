#include "omni.h"
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void arena_init(Arena *a){ a->head=NULL; }
void *arena_alloc(Arena *a, size_t n){
    size_t want; ArenaChunk *c;
    n = (n+7)&~(size_t)7;
    c=a->head;
    if(!c || c->len + n > c->cap){
        want = n>4096? n:4096;
        c=malloc(sizeof(ArenaChunk)+want);
        if(!c){ fprintf(stderr,"omni: out of memory\n"); exit(1); }
        c->next=a->head; c->len=0; c->cap=want; a->head=c;
    }
    c->len+=n;
    return c->data + c->len - n;
}
char *arena_dupn(Arena *a, const char *s, size_t n){
    if(!a){ char *out=malloc(n+1); memcpy(out,s,n); out[n]='\0'; return out; }
    char *out=arena_alloc(a,n+1); memcpy(out,s,n); out[n]='\0'; return out;
}
char *arena_dup(Arena *a, const char *s){
    if(!a) return strdup(s);
    return arena_dupn(a,s,strlen(s));
}
void arena_free(Arena *a){
    ArenaChunk *c=a->head,*next;
    while(c){ next=c->next; free(c); c=next; }
    a->head=NULL;
}

void say(Interp *ip, const char *msg){
    size_t n=strlen(msg);
    while(n && (msg[n-1]=='\n' || msg[n-1]=='\r')) n--;
    fwrite(msg,1,n,ip->out); fputc('\n',ip->out); fflush(ip->out);
}
void say_text(Interp *ip, const char *text){
    size_t n=strlen(text); if(!n) return;
    fwrite(text,1,n,ip->out);
    if(text[n-1]!='\n') fputc('\n',ip->out);
    fflush(ip->out);
}
void fail_at(Interp *ip, int line, int col, const char *fmt, ...){
    va_list ap; va_start(ap,fmt); vsnprintf(ip->errmsg,sizeof(ip->errmsg),fmt,ap); va_end(ap);
    ip->errline=line; ip->errcol=col; longjmp(ip->jb,1);
}
const char *line_text(const char *src, int line, char *buf, size_t cap){
    int cur=1; const char *p=src,*start=src;
    if(line<1||cap==0) return "";
    while(*p && cur<line){ if(*p=='\n'){cur++; start=p+1;} p++; }
    if(cur!=line) return "";
    p=start; while(*p && *p!='\n' && (size_t)(p-start)+1<cap){ buf[p-start]=*p; p++; }
    buf[p-start]='\0'; return buf;
}
void num_text(double num, int is_int, char *buf, size_t cap){
    if(is_int) snprintf(buf,cap,"%lld",(long long)num);
    else snprintf(buf,cap,"%g",num);
}

/* env */
void env_set(Env *e, const char *name, Value *v){
    Binding *b=e->head;
    while(b){ if(strcmp(b->name,name)==0){ b->val=v; return; } b=b->next; }
    b=malloc(sizeof(Binding));
    b->name=strdup(name);
    b->val=v;
    b->next=e->head;
    e->head=b;
}
void env_set_heap(Env *e, const char *name, Value *v){
    Binding *b=malloc(sizeof(Binding));
    b->name=(char*)name;
    b->val=v;
    b->next=e->head;
    e->head=b;
}
Value *env_get(Env *e, const char *name){
    Binding *b=e->head;
    while(b){ if(strcmp(b->name,name)==0) return b->val; b=b->next; }
    return NULL;
}
int env_has(Env *e, const char *name){ return env_get(e,name)!=NULL; }

/* values - use malloc for persistence */
static Value *val_alloc(void){
    Value *v=malloc(sizeof(Value));
    memset(v,0,sizeof(Value));
    return v;
}
Value *val_nil(Interp *ip){
    (void)ip;
    Value *v=val_alloc(); v->kind=V_NIL; return v;
}
Value *val_num(Interp *ip, double n, int is_int){
    (void)ip;
    Value *v=val_alloc(); v->kind=V_NUM; v->num=n; v->is_int=is_int; return v;
}
Value *val_str(Interp *ip, const char *s){
    (void)ip;
    Value *v=val_alloc(); v->kind=V_STR; v->str=strdup(s); return v;
}
Value *val_bool(Interp *ip, int b){
    (void)ip;
    Value *v=val_alloc(); v->kind=V_BOOL; v->boolean=b?1:0; return v;
}
Value *val_tuple(Interp *ip, Value **items, int n){
    (void)ip;
    Value *v=val_alloc(); v->kind=V_TUPLE; v->items=items; v->nitems=n; return v;
}
Value *val_module(Interp *ip, const char *name, BuiltinFunc call){
    (void)ip;
    Value *v=val_alloc(); v->kind=V_MODULE; v->mod_name=strdup(name); v->mod_call=call;
    v->env=malloc(sizeof(Env)); v->env->head=NULL; return v;
}
Value *val_func(Interp *ip, const char *name, BuiltinFunc fn){
    (void)ip;
    Value *v=val_alloc(); v->kind=V_FUNC; v->func_name=strdup(name); v->func=fn; return v;
}
Value *val_func_bound(Interp *ip, const char *name, BuiltinFunc fn, Value *bound){
    (void)ip;
    Value *v=val_alloc(); v->kind=V_FUNC; v->func_name=strdup(name); v->func=fn; v->bound=bound; return v;
}
Value *val_path(Interp *ip, const char *path){
    (void)ip;
    Value *v=val_alloc(); v->kind=V_PATH; v->str=strdup(path); return v;
}
Value *val_element(Interp *ip, Element *el){
    (void)ip;
    Value *v=val_alloc(); v->kind=V_ELEMENT; v->elem=el; return v;
}
const char *val_to_string(Interp *ip, Value *v){
    char buf[128];
    if(!v) return "nil";
    switch(v->kind){
        case V_NIL: return "nil";
        case V_BOOL: return v->boolean?"True":"False";
        case V_NUM: {
            num_text(v->num,v->is_int,buf,sizeof(buf));
            if(ip && ip->arena) return arena_dup(ip->arena,buf);
            return strdup(buf);
        }
        case V_STR: return v->str;
        case V_PATH: return v->str;
        case V_TUPLE: {
            // build string, use arena if available else malloc
            size_t cap=64,len=1;
            char *out;
            if(ip && ip->arena) out=arena_alloc(ip->arena,cap);
            else { out=malloc(cap); }
            int i;
            out[0]='(';
            for(i=0;i<v->nitems;i++){
                const char *s=val_to_string(ip,v->items[i]);
                size_t n=strlen(s);
                while(len+n+3>cap){
                    cap*=2;
                    if(ip && ip->arena){
                        char *b=arena_alloc(ip->arena,cap);
                        memcpy(b,out,len);
                        out=b;
                    } else {
                        out=realloc(out,cap);
                    }
                }
                if(i){ out[len++]=','; out[len++]=' '; }
                memcpy(out+len,s,n); len+=n;
            }
            out[len++]=')'; out[len]='\0'; return out;
        }
        case V_MODULE: return v->mod_name;
        case V_FUNC: return v->func_name;
        case V_ELEMENT: return "<element>";
    }
    return "";
}
int val_to_int(Value *v, int def){
    if(!v) return def;
    if(v->kind==V_NUM) return (int)v->num;
    if(v->kind==V_BOOL) return v->boolean?1:0;
    if(v->kind==V_STR){ char *e; long l=strtol(v->str,&e,10); if(e!=v->str) return (int)l; }
    return def;
}
double val_to_num(Value *v, double def){
    if(!v) return def;
    if(v->kind==V_NUM) return v->num;
    if(v->kind==V_BOOL) return v->boolean?1:0;
    if(v->kind==V_STR){ char *e; double d=strtod(v->str,&e); if(e!=v->str) return d; }
    return def;
}
int val_is_truthy(Value *v){
    if(!v) return 0;
    switch(v->kind){
        case V_NIL: return 0;
        case V_BOOL: return v->boolean;
        case V_NUM: return v->num!=0;
        case V_STR: return v->str[0]!='\0';
        case V_PATH: return v->str[0]!='\0';
        case V_TUPLE: return v->nitems!=0;
        default: return 1;
    }
}

/* color parsing */
#include <ctype.h>
static const struct { const char *name, *hex; } NAMED[] = {
    {"black","#000000"},{"white","#ffffff"},{"red","#e5534b"},{"green","#2ea043"},{"blue","#58a6ff"},
    {"yellow","#f2cc60"},{"orange","#f0883e"},{"purple","#a371f7"},{"pink","#ff7b9c"},{"cyan","#39c5cf"},
    {"teal","#1f6feb"},{"navy","#0d1b3d"},{"grey","#8b949e"},{"gray","#8b949e"},{"silver","#c9d1d9"},
    {"gold","#e3b341"},{"brown","#8b5a2b"},{"lime","#7ee787"},{"maroon","#8b2635"},{"olive","#7d8c34"},
    {NULL,NULL}
};
static int hexval(char c){ if(c>='0'&&c<='9') return c-'0'; if(c>='a'&&c<='f') return c-'a'+10; if(c>='A'&&c<='F') return c-'A'+10; return -1; }
int parse_color(const char *s, unsigned char out[3]){
    char norm[64]; size_t i,n; const char *p=s;
    if(!p||!*p) return 0;
    n=strlen(p); if(n>=sizeof(norm)) n=sizeof(norm)-1;
    for(i=0;i<n;i++) norm[i]=tolower((unsigned char)p[i]);
    norm[n]='\0';
    for(i=0;NAMED[i].name;i++) if(strcmp(norm,NAMED[i].name)==0){ p=NAMED[i].hex; n=7; memcpy(norm,p,8); break; }
    if(norm[0]=='#'&&n==7&&hexval(norm[1])>=0&&hexval(norm[2])>=0&&hexval(norm[3])>=0&&hexval(norm[4])>=0&&hexval(norm[5])>=0&&hexval(norm[6])>=0){
        out[0]=(unsigned char)(hexval(norm[1])*16+hexval(norm[2]));
        out[1]=(unsigned char)(hexval(norm[3])*16+hexval(norm[4]));
        out[2]=(unsigned char)(hexval(norm[5])*16+hexval(norm[6]));
        return 1;
    }
    if(norm[0]=='#'&&n==4&&hexval(norm[1])>=0&&hexval(norm[2])>=0&&hexval(norm[3])>=0){
        out[0]=(unsigned char)(hexval(norm[1])*17);
        out[1]=(unsigned char)(hexval(norm[2])*17);
        out[2]=(unsigned char)(hexval(norm[3])*17);
        return 1;
    }
    return 0;
}
