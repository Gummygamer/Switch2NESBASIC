"""Small host evaluator for the numeric BASIC subset used by CPU/bus routines.

This is a logic test aid, not a SmileBASIC compatibility emulator. In particular
it cannot validate console graphics, controller APIs or the real BASIC parser.
"""
import operator
import re
from collections import defaultdict

TOKEN = re.compile(r'\s*(\d+|[A-Z_][A-Z_0-9]*|<<|>>|==|!=|<=|>=|[\[\]()+*/%<>&|^~,-])')
BIN = {
    'OR':(1,operator.or_), 'XOR':(2,operator.xor), 'AND':(3,operator.and_),
    '==':(4,lambda a,b:int(a==b)), '!=':(4,lambda a,b:int(a!=b)),
    '<':(4,lambda a,b:int(a<b)), '>':(4,lambda a,b:int(a>b)),
    '<=':(4,lambda a,b:int(a<=b)), '>=':(4,lambda a,b:int(a>=b)),
    '<<':(5,operator.lshift), '>>':(5,operator.rshift),
    '+':(6,operator.add), '-':(6,operator.sub),
    '*':(7,operator.mul), 'DIV':(7,operator.floordiv), 'MOD':(7,operator.mod),
}

class BasicVM:
    def __init__(self, source):
        self.v=defaultdict(int)
        self.a={name:[0]*size for name,size in [('RAM',2048),('SRAM',8192),('ROM',786960),('CHR',8192),('NT',4096),('PAL',32),('OAM',256),('OT',256),('MT',256),('CT',256),('PT',256),('BG',256),('PIX',256),('USED',256),('COL',64),('BANKREG',8),('PRGBANK',4),('CHRBANK',8),('SPR12',8)]}
        self.lines=[]; self.labels={}; self.block_end={}; self.block_else={}
        stack=[]
        for raw in source.splitlines():
            line=raw.strip()
            if not line or line.startswith("'"): continue
            if line.startswith('@'):
                self.labels[line[1:]]=len(self.lines); continue
            i=len(self.lines); self.lines.append(line)
            if line.startswith('IF ') and line.endswith(' THEN'):
                stack.append(i)
            elif line=='ELSE':
                self.block_else[stack[-1]]=i
            elif line=='ENDIF':
                start=stack.pop(); self.block_end[start]=i
                if start in self.block_else: self.block_end[self.block_else[start]]=i
        assert not stack
        self.cache={}
        self.loop_end={}; loop_stack=[]; self.pixels={}
        for i,line in enumerate(self.lines):
            if line.startswith('FOR ') and not line.endswith(':NEXT'): loop_stack.append(i)
            elif line=='NEXT':
                start=loop_stack.pop();self.loop_end[start]=i
        assert not loop_stack
        self.while_end={}; while_stack=[]
        for i,line in enumerate(self.lines):
            if line.startswith('WHILE '): while_stack.append(i)
            elif line=='WEND':
                start=while_stack.pop();self.while_end[start]=i;self.while_end[i]=start
        assert not while_stack

    def expr(self, text):
        if text not in self.cache:
            tokens=TOKEN.findall(text)
            if ''.join(tokens) != re.sub(r'\s+','',text): raise ValueError(text)
            pos=0
            def parse(minp=0):
                nonlocal pos
                t=tokens[pos]; pos+=1
                if t in ('NOT','-','+'):
                    arg=parse(8)
                    node=('unary',t,arg)
                elif t=='(':
                    node=parse(); assert tokens[pos]==')'; pos+=1
                elif t.isdigit(): node=('num',int(t))
                else:
                    node=('var',t)
                    if pos<len(tokens) and tokens[pos]=='[':
                        pos+=1; index=parse(); assert tokens[pos]==']'; pos+=1
                        node=('arr',t,index)
                while pos<len(tokens) and tokens[pos] in BIN and BIN[tokens[pos]][0]>=minp:
                    op=tokens[pos]; pos+=1
                    node=('bin',op,node,parse(BIN[op][0]+1))
                return node
            node=parse(); assert pos==len(tokens),(text,tokens[pos:])
            self.cache[text]=node
        def ev(n):
            kind=n[0]
            if kind=='num': return n[1]
            if kind=='var': return self.v[n[1]]
            if kind=='arr': return self.a[n[1]][ev(n[2])]
            if kind=='bin': return BIN[n[1]][1](ev(n[2]),ev(n[3]))
            x=ev(n[2]); return ~x if n[1]=='NOT' else -x if n[1]=='-' else x
        return ev(self.cache[text])

    def inline(self,line):
        # IF controls the remainder of its source line, including colon statements.
        if line.startswith('IF '):
            condition,rest=line[3:].split(' THEN ',1)
            yes,sep,no=rest.partition(' ELSE ')
            return self.inline(yes if self.expr(condition) else no) if sep or self.expr(condition) else False
        first,sep,rest=line.partition(':')
        if first=='RETURN': return True
        if first in ('CONTINUE','BREAK'): return first
        if first.startswith('GLOAD '):
            x,y,w,h,indices,palette,mode=first[6:].split(',')
            x,y,w,h=map(self.expr,(x,y,w,h))
            assert self.expr(mode)==0
            for offset in range(w*h):
                self.pixels[x+offset%w,y+offset//w]=self.a[palette][self.a[indices][offset]]
            return self.inline(rest) if sep else False
        if first.startswith('GPSET '):
            x,y,c=map(self.expr,first[6:].split(','));self.pixels[x,y]=c
            return self.inline(rest) if sep else False
        if first.startswith('GOSUB @'): self.call(first[7:])
        elif first.startswith('PRINT ') or first=='END': raise RuntimeError(first)
        else:
            lhs,rhs=first.split('=',1)
            val=self.expr(rhs)
            if '[' in lhs:
                name,index=lhs[:-1].split('[',1); self.a[name][self.expr(index)]=val
            else: self.v[lhs]=val
        return self.inline(rest) if sep else False

    def call(self,label):
        pc=self.labels[label]; loops=[]
        while True:
            line=self.lines[pc]
            if line.startswith('IF ') and line.endswith(' THEN'):
                if not self.expr(line[3:-5]):
                    pc=self.block_else.get(pc,self.block_end[pc])+1; continue
            elif line=='ELSE': pc=self.block_end[pc]+1; continue
            elif line=='ENDIF': pass
            elif line.startswith('WHILE '):
                if not self.expr(line[6:]): pc=self.while_end[pc]+1;continue
            elif line=='WEND': pc=self.while_end[pc];continue
            elif line.startswith('FOR '):
                name,values=line[4:].split('=',1);start,end=values.split(' TO ')
                self.v[name]=self.expr(start);limit=self.expr(end)
                if self.v[name]>limit: pc=self.loop_end[pc]+1;continue
                loops.append((pc,name,limit))
            elif line=='NEXT':
                start,name,limit=loops[-1];self.v[name]+=1
                if self.v[name]<=limit: pc=start+1;continue
                loops.pop()
            else:
                signal=self.inline(line)
                if signal is True: return
                if signal=='CONTINUE': pc=self.loop_end[loops[-1][0]];continue
                if signal=='BREAK': pc=self.loop_end[loops.pop()[0]]+1;continue
            pc+=1
