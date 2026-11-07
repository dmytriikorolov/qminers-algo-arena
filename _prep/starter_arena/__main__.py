"""Offline starter examples for four plausible challenge families.
Run: python3 -m starter_arena all-demos
These examples use synthetic data only and prove no competitive edge.
"""
import argparse
import json
import math
import random
import sys
from collections import defaultdict


def market_demo(seed=42):
    rng = random.Random(seed)
    cash = 0.0
    inventory = 0
    trades = 0
    price = 100.0
    for _ in range(200):
        price += rng.choice([-0.2, 0, 0.2])
        bid = round(price - 0.1, 2)
        ask = round(price + 0.1, 2)
        # Explicitly synthetic hypothetical fill model: randomly fill one posted quote.
        signal = rng.choice([-1, 0, 0, 1])
        if signal == -1 and inventory < 5:
            cash -= bid
            inventory += 1
            trades += 1
        elif signal == 1 and inventory > -5:
            cash += ask
            inventory -= 1
            trades += 1
    return {'family':'market','synthetic':True,'pnl':round(cash + inventory*price, 2),
            'position':inventory,'trades':trades,'fill_assumption':'random heuristic'}


def ml_demo():
    # Deterministic toy majority-vote baseline, no sklearn dependency.
    train_y=[0,1,0,0,1,0,1,0,0,1,0,0]
    test_y=[0,1,0,1,0,0]
    majority=int(sum(train_y)*2>len(train_y))
    acc=sum(y==majority for y in test_y)/len(test_y)
    return {'family':'ml','synthetic':True,'baseline':'majority class',
            'test_accuracy':round(acc,4),'test_rows':len(test_y)}


def allocations(total, values, caps):
    # Exhaustive search: small problems only. Serves as an exact oracle.
    best=(-float('inf'),None)
    def rec(i,remain,choice):
        nonlocal best
        if i==len(values):
            if remain==0:
                score=sum(v*x for v,x in zip(values,choice))
                if score>best[0]:best=(score,tuple(choice))
            return
        for x in range(min(remain,caps[i])+1):
            rec(i+1,remain-x,choice+[x])
    rec(0,total,[])
    return best


def game_demo():
    total=8; values=[3,5,4]; caps=[4,3,5]
    value,alloc=allocations(total,values,caps)
    return {'family':'resource_game','synthetic':True,'budget':total,
            'allocations':list(alloc),'score':value,'method':'exact enumeration'}


def shortest_path(graph,start,goal):
    # Dijkstra on a nonnegative graph, basic pure Python implementation.
    import heapq
    heap=[(0,start)]; dist={start:0}
    while heap:
        cost,node=heapq.heappop(heap)
        if cost!=dist.get(node): continue
        if node==goal: return cost
        for next_node,weight in graph.get(node,[]):
            if weight<0:raise ValueError('negative weight')
            nxt=cost+weight
            if nxt<dist.get(next_node,math.inf):
                dist[next_node]=nxt
                heapq.heappush(heap,(nxt,next_node))
    return None


def coding_demo():
    edges={'A':[('B',4),('C',1)],'C':[('B',1),('D',5)],'B':[('D',2)]}
    return {'family':'coding','synthetic':True,'shortest_A_to_D':shortest_path(edges,'A','D')}


def main(argv=None):
    p=argparse.ArgumentParser(prog='starter_arena')
    p.add_argument('command',choices=['doctor','market-demo','ml-demo','game-demo','code-demo','all-demos'])
    args=p.parse_args(argv)
    mapping={'market-demo':market_demo,'ml-demo':ml_demo,'game-demo':game_demo,'code-demo':coding_demo}
    if args.command=='doctor':
        print(json.dumps({'python':sys.version.split()[0],'ready':True,'note':'No dependency means only starter checks passed.'},indent=2))
    elif args.command=='all-demos':
        print(json.dumps([fn() for fn in mapping.values()],indent=2))
    else: print(json.dumps(mapping[args.command](),indent=2))

if __name__=='__main__': main()
