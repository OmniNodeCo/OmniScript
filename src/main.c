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

static void usage(FILE *f){
    fprintf(f,"OmniScript %s -- super simple\n\n"
            "  omni FILE         run a script\n"
            "  omni -e CODE      run one line\n"
            "  omni --version    version\n"
            "  omni --help       help\n"
            "  omni              REPL\n\n"
            "Language:\n"
            "  import draw, cmd, pathlib\n"
            "  from draw import window, rect, button, show\n"
            "  draw.window(640,400,\"Demo\")\n"
            "  draw.rect(0,0,100,100,\"red\")\n"
            "  draw.button(10,10,100,30,\"Click\", action=\"ls\")\n"
            "  draw.show()  # or draw() \n"
            "  cmd.run(\"ls -la\")\n"
            "  cmd.bg(\"sleep 10\")\n"
            "  pathlib.write(\"a.txt\",\"hi\")\n"
            "  pathlib.read(\"a.txt\")\n"
            "  pathlib.exists(\"a.txt\")\n"
            "  print(\"hello\")\n",OMNI_VERSION);
}

static char *read_script(const char *path){
    FILE *f=fopen(path,"rb"); if(!f) return NULL;
    size_t cap=8192,len=0,n; char *buf=malloc(cap);
    if(!buf){ fclose(f); return NULL; }
    for(;;){
        if(len+1024>cap){ char *b=realloc(buf,cap*2); if(!b){ free(buf); fclose(f); return NULL; } buf=b; cap*=2; }
        n=fread(buf+len,1,1023,f); len+=n; if(n<1023) break;
    }
    buf[len]='\0'; fclose(f); return buf;
}
static int run_file(Interp *ip, const char *path){
    char *src=read_script(path); if(!src){ fprintf(stderr,"omni: cannot read %s: %s\n",path,strerror(errno)); return 1; }
    int rc=run_source(ip,src,path); free(src); return rc;
}

static void repl_help(void){
    printf("Type lines, they run. help, exit\n"
           "  import draw\n"
           "  draw.window(320,200,\"Hi\")\n"
           "  draw.rect(0,0,100,100,\"red\")\n"
           "  draw.show()\n"
           "  import cmd\n"
           "  cmd.run(\"ls\")\n"
           "  import pathlib\n"
           "  pathlib.write(\"a.txt\",\"hi\")\n");
}

static int repl(Interp *ip){
    char *acc=NULL; size_t acap=0,alen=0; int parens=0;
    printf("OmniScript %s -- type help, exit\n",OMNI_VERSION);
    for(;;){
        char line[4096];
        fputs(alen?".... ":"omni> ",stdout); fflush(stdout);
        if(!fgets(line,sizeof(line),stdin)){ putchar('\n'); break; }
        size_t n=strlen(line);
        if(alen+n+1>acap){ size_t ncap=acap?acap*2:4096; while(ncap<alen+n+1) ncap*=2; char *b=realloc(acc,ncap); if(!b){ fprintf(stderr,"omni: oom\n"); free(acc); return 1; } acc=b; acap=ncap; }
        memcpy(acc+alen,line,n+1); alen+=n;
        // simple paren balance
        for(size_t i=0;i<n;i++){ if(line[i]=='(') parens++; else if(line[i]==')') parens--; }
        if(parens>0) continue;
        char *cmd=acc; while(*cmd==' '||*cmd=='\t'||*cmd=='\n') cmd++;
        size_t cn=strlen(cmd); while(cn && (cmd[cn-1]=='\n'||cmd[cn-1]==' '||cmd[cn-1]=='\t')) cmd[--cn]='\0';
        if(!*cmd){ alen=0; parens=0; if(acc) acc[0]='\0'; continue; }
        if(strcmp(cmd,"exit")==0||strcmp(cmd,"quit")==0) break;
        if(strcmp(cmd,"help")==0) repl_help();
        else run_source(ip,acc,"<repl>");
        alen=0; parens=0; if(acc) acc[0]='\0';
    }
    free(acc);
    return 0;
}

int main(int argc, char **argv){
    Interp ip; char cwd[4096]; int rc;
    if(!getcwd(cwd,sizeof(cwd))) strcpy(cwd,".");
    interp_init(&ip,stdout,cwd);
    modules_init(&ip);
    if(argc<2) rc=repl(&ip);
    else if(strcmp(argv[1],"--version")==0||strcmp(argv[1],"-V")==0){ printf("%s\n",OMNI_VERSION); rc=0; }
    else if(strcmp(argv[1],"--help")==0||strcmp(argv[1],"-h")==0){ usage(stdout); rc=0; }
    else if(strcmp(argv[1],"-e")==0){
        if(argc<3){ fprintf(stderr,"omni: -e needs code\n"); rc=2; }
        else if(argc>3){ fprintf(stderr,"omni: unexpected arg '%s'\n",argv[3]); rc=2; }
        else rc=run_source(&ip,argv[2],"-e");
    } else if(argv[1][0]=='-'){ fprintf(stderr,"omni: unknown option '%s'\n",argv[1]); usage(stderr); rc=2; }
    else if(argc>2){ fprintf(stderr,"omni: unexpected arg '%s'\n",argv[2]); rc=2; }
    else rc=run_file(&ip,argv[1]);
    interp_free(&ip);
    return rc;
}
