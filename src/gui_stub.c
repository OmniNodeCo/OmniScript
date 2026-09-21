#include "omni.h"
int gui_available(void){ return 0; }
int gui_show(Interp *ip, Element *elems, int nelems, int w, int h, const char *title, const unsigned char bg[3]){
    (void)ip;(void)elems;(void)nelems;(void)w;(void)h;(void)title;(void)bg;
    return 0;
}
