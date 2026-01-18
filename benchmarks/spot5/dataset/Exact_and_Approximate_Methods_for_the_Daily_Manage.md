# EXACT AND APPROXIMATE METHODS FOR THE DAILY MANAGEMENT OF AN EARTH OBSERVATION SATELLITE

J.C. Agnès, N. Bataille, D. Blumstein (†)

E. Bensana, G. Verfaillie  $(\ddagger)$

†: CNES, Centre Spatial de Toulouse, 18 av E. Belin, 31055 Toulouse Cedex, France

$\ddagger$  : CERT-ONERA, 2, av. E. Belin, BP 4025, 31055 Toulouse Cedex, France

# ABSTRACT

The daily management of a remote sensing satellite like Spot, which consists in deciding every day what photographs will be attempted the next day, is of a great economical importance. But it is a large and difficult combinatorial optimization problem, for which efficient search methods have to be built and assessed.

In this paper we describe the problem in the framework of the future Spot5 satellite. Then we show that this problem can be viewed as an instance of the Valued Constraint Satisfaction Problem framework, which allows hard and soft constraints to be expressed together and dealt with.

After that we describe several methods which can be used in this framework: exact methods like Depth First Branch and Bound or Pseudo Dynamic Search to find an optimal solution and approximate methods like Greedy Search or Tabu Search to find a good solution.

Finally, we compare the results obtained with these methods on a set of representative problems. The conclusion addresses some lessons which can be drawn from this overview.

Keywords : Valued Constraint Satisfaction, Constrained Optimization, Branch and Bound, Greedy Search, Tabu Search.

# 1 PROBLEM MODELING

# 1.1 The Scheduling Problem

The Spot5 daily scheduling problem [1] can be informally described as follows :

- given a set  $S$  of photographs, mono or stereo, which can be attempted the next day w.r.t. the satellite trajectory;

- given a weight associated to each photograph, which is the result of the aggregation of several criteria like the client importance, the demand urgency, the meteorological forecasts ...

- given a set of possibilities associated to each photograph corresponding to the different ways to achieve it: up to three for a mono photograph (because of the three instruments on the satellite) and only one for a stereo (because such photographs require two trials: one with the front instrument and one with the rear one):

- given a set of hard constraints, which must be satisfied :

- non overlapping and respect of the minimal transition time between two successive trials on the same instrument;

- limitation of the instantaneous data flow through the satellite telemetry;

- limitation of the recording capacity on board;

- the problem is to find a subset  $S'$  of  $S$  which is admissible (hard constraints met) and which maximizes the sum of the weights of the photographs in  $S'$ .

This problem clearly belongs to the class of the Discrete Constrained Optimization Problems.

# 1.2 Modeling as a Valued Constraint Satisfaction Problem

# 1.2.1 The VCSP framework

The Valued Constraint Satisfaction Problem framework (VCSP) [2, 3] is an extension of the CSP framework, where each problem can be characterized by:

- a set  $V$  of variables: a finite domain of values is associated to each variable and defines its possible instantiations;

- a set  $C$  of constraints: each constraint links a subset  $V'$  of the variables and defines forbidden combinations of values for the variables in  $V'$ ;

- a valuation set  $E$  (to valuate constraints and assignments), with a total order  $\succ$  (to compare two valuations), a minimal element  $\bot$  (to represent constraint satisfaction) and a maximal one  $\top$  (to represent violation of a hard constraint):

- a valuation function  $\varphi$ , associating to each constraint  $c$  in  $C$  an element  $\varphi(c)$  in  $E$ , which represents the importance of the satisfaction of  $c$ ;

- an aggregation operator  $\otimes$  (to aggregate constraints valuations), which respects :

commutativity and associativity;

monotonicity relatively to the order  $\succ$

-  $\perp$  identity;

- T absorbing element.

Given an assignment  $A$  of all the problem variables, the valuation of  $A$  is the aggregation by the operator  $\otimes$  of the valuations of all the constraints not satisfied by  $A$ :

$$
v (A) = \otimes_ {c \in C, c n o t s a t i s f i e d b y A} [ \varphi (c) ]
$$

The standard objective is to produce an assignment with a minimal valuation. It is an NP-hard problem, according to the complexity theory, and then its worst-case complexity grows at least exponentially with the problem size.

Table 1 describes some frameworks w.r.t the combination of the valuation set  $E$ , the order  $\succ$ , the minimal element  $\bot$ , the maximal element  $\top$  and the aggregation operator  $\otimes$ .

<table><tr><td>Framework</td><td>Label</td><td>E</td><td>\( \succ \)</td><td>⊥</td><td>T</td><td>⊗</td></tr><tr><td>Standard</td><td>∧-VCSP</td><td>{true,false}</td><td>false \( \succ \) true</td><td>true</td><td>false</td><td>∧</td></tr><tr><td>Possibilistic</td><td>Max-VCSP</td><td>[0,1]</td><td>&gt;</td><td>0</td><td>1</td><td>max</td></tr><tr><td>Additive</td><td>\( \sum -VCSP \)</td><td>N∪{+∞}</td><td>&gt;</td><td>0</td><td>+∞</td><td>+</td></tr></table>

Table 1: Some CSP frameworks

Other frameworks like II-VCSP (probabilistic CSP) or Lex-VCSP (lexicographic CSP) can be characterized in the same way.

# 1.2.2 Modeling

The modeling of the Spot5 scheduling problems within the VCSP framework [4] consists in:

- associating a variable  $v$  to each photograph  $p$ ;

- associating to  $v$  a domain  $d$  of values corresponding to the different possibilities to achieve  $p$ :

- a subset of  $\{1,2,3\}$  for a mono photograph (values 1, 2 et 3 corresponding to the possibility of using the front, middle or rear instrument to take the photograph);

- the only value 13 for a stereo photograph (corresponding to the only possibility, with both the front and rear instruments);

- adding to  $d$ , the special value 0 corresponding to the possibility of not selecting  $p$  in the schedule;

- associating to  $v$  a unary constraint forbidding the special value 0, with a valuation equal to the weight of  $p$  (the penalty for not selecting  $p$ );

- translating as binary constraints, with the maximal valuation  $\top$ , the constraints of non overlapping and respect of the minimal transition time between two trials on the same instrument;

- translating as binary or ternary constraints, with the maximal valuation  $\top$ , the constraints of limitation of the instantaneous data flow;

- translating as an  $n$ -ary constraint, with the maximal valuation  $\top$ , the constraint of limitation of the recording capacity;

- using as valuation set the set of integers between 0 (⊥) and an integer greater than the sum of the weights of all the photographs (T);

- using as order the natural order on integers and as aggregation operator the usual  $+$  operator.

With this modeling, the valuation of an assignment  $A$  is equal to  $\top$  when a hard constraint is not satisfied or equal to the sum of the weights of the rejected photographs when all the hard constraints are met. As it is always possible to produce an assignment where all the hard constraints are satisfied (for example by rejecting all the photographs), finding an assignment of minimal valuation is equivalent to finding an assignment satisfying all the hard constraints and minimizing the sum of the weights of the rejected photographs.

About the resulting VCSP, we can note that the domains are at most of size 4 ( $\{0,1,2,3\}$ ) for mono photographs and of size 2 ( $\{0,13\}$ ) for stereo photographs. Except the unary constraints associated to each variable (the only ones which can be violated), all the other constraints are hard (valuation equal to  $\top$ ). The valuation set and aggregation operator induce an additive VCSP. Well, additive VCSP are, with probabilistic and lexicographic VCSP, the most difficult ones to solve, much more difficult than classic and possibilistic VCSP [2, 3].

Table 2 shows the variables and table 3 the constraints of the VCSP corresponding to a toy problem.

<table><tr><td>Name</td><td>Domain</td></tr><tr><td>S129703-1</td><td>1 2 3 0</td></tr><tr><td>S129702-1</td><td>1 2 3 0</td></tr><tr><td>S129701-1</td><td>1 2 3 0</td></tr><tr><td>S129701-2</td><td>1 2 3 0</td></tr><tr><td>S17302-1</td><td>13 0</td></tr><tr><td>S17301-1</td><td>13 0</td></tr><tr><td>S17302-2</td><td>13 0</td></tr><tr><td>S17302-3</td><td>13 0</td></tr></table>

Table 2: Variables of the toy problem

Table 4 summarizes information about the VCSP corresponding to the biggest problems from our data set (see §4.1 for a description of the data set):

-  $Pb$  is the problem number;

-  $N_{val}$  is the number of possible trials;

-  $N_{var}$  is the number of possible photographs (variables);

-  $N_{c_i}$  is the number of constraints of arity  $i$ ;

<table><tr><td>Linked Variables</td><td>Forbidden tuples</td><td>Valuation</td></tr><tr><td>(S129703-1)</td><td>(0)</td><td>1</td></tr><tr><td>(S129702-1)</td><td>(0)</td><td>1</td></tr><tr><td>(S129701-1)</td><td>(0)</td><td>1</td></tr><tr><td>(S129701-2)</td><td>(0)</td><td>1</td></tr><tr><td>(S17302-1)</td><td>(0)</td><td>2</td></tr><tr><td>(S17301-1)</td><td>(0)</td><td>2</td></tr><tr><td>(S17302-2)</td><td>(0)</td><td>2</td></tr><tr><td>(S17302-3)</td><td>(0)</td><td>2</td></tr><tr><td>(S17302-1 S17301-1)</td><td>(13 13)</td><td>T</td></tr><tr><td>(S17302-2 S17301-1)</td><td>(13 13)</td><td>T</td></tr><tr><td>(S129703-1 S129702-1)</td><td>(3 3) (2 2) (1 1)</td><td>T</td></tr><tr><td>(S129702-1 S129701-1)</td><td>(3 3) (2 2) (1 1)</td><td>T</td></tr><tr><td>(S129702-1 S129701-2)</td><td>(3 3) (2 2) (1 1)</td><td>T</td></tr><tr><td>(S129703-1 S129701-1)</td><td>(3 3) (2 2) (1 1)</td><td>T</td></tr><tr><td>(S129703-1 S129701-2)</td><td>(3 3) (2 2) (1 1)</td><td>T</td></tr></table>


Table 3: Constraints of the toy problem


-  $N_{ct}$  is the total number of constraints;

-  $T_{cpu}$  is the cpu time needed to create the VCSP.

<table><tr><td>Pb</td><td>Nval</td><td>Nvar</td><td>Nc1</td><td>Nc2</td><td>Nc3</td><td>Nct</td><td>Tcpu</td></tr><tr><td>11</td><td>874</td><td>364</td><td>364</td><td>5025</td><td>4719</td><td>10065</td><td>345</td></tr><tr><td>1021</td><td>2517</td><td>1057</td><td>1057</td><td>14854</td><td>5875</td><td>21786</td><td>1002</td></tr></table>

Table 4: VCSP characteristics for problems 11 et 1021

# 2 EXACT METHODS

Exact methods are systematic tree search procedures. The root of the tree, starting point for the search, is the empty assignment. At each node, the set of variables is partitioned into a set of instantiated variables and a set of uninstantiated variables. The children of a node correspond to all the possible extensions of the current assignment by instantiating a new variable. The leaves of the tree correspond to all the possible assignments. Variable instantiation ordering and value ordering can be used to guide the search. These methods are called exact, because they are able to find an optimal solution, provided that no running time limit is set. To avoid producing and evaluating all the possible assignments, optimistic evaluations of the partial assignments are used:

Definition 1 The partial assignment valuation  $vp$  is said to be optimistic iff  $\forall A$ , partial assignment,  $\forall A'$ , complete extension of  $A$  over the set of variables,  $v(A') \succeq vp(A)$ .

Consequently, the following property holds:

Property 1 Given  $vp$  an optimistic partial assignment valuation; given  $A$  a complete assignment with valuation  $v(A)$ ; given  $A'$  a partial assignment with valuation  $vp(A')$ ; if  $vp(A') \succeq v(A)$ , then  $\forall A''$ , complete extension of  $A'$ ,  $v(A'') \succeq vp(A') \succeq v(A)$ .

All methods based on Branch and Bound use that property to cut into the tree search. It can easily be shown that the more realistic the partial assignment valuation is, the better the cuts are.

# 2.1 Strategies

# 2.1.1 Depth First Branch and Bound

The most frequently used algorithm is the Depth First Branch and Bound, which can be viewed as an extension to the VCSP framework of the Backtrack algorithm, widely used within the standard CSP framework [2].

Let us assume, that the problem is to find an assignment with a minimal valuation, less than  $\alpha_{init}$  and greater than or equal to  $\beta$  (we suppose that it is known by other means that no assignment with valuation less than  $\beta$  exists). By default,  $\alpha_{init} = \top$  and  $\beta = \bot$ . The mechanism consists in performing a depth first search to find a complete assignment with a valuation less than  $\alpha$ . This bound, initialized to  $\alpha_{init}$ , strictly decreases during search. Each time a complete assignment with a valuation less than the current bound is found, its valuation is used as a new bound. Each time a partial assignment with a valuation greater than or equal to the current bound is produced, a backtrack occurs (property 1 used to cut into the search space). The algorithm stops when a complete assignment of valuation equal to  $\beta$  is found or when no complete assignment of valuation less than the current bound can be found. Figure 1 more precisely describes this algorithm.

```prolog
DFBB  $(p,\alpha_{init},\beta)$    
; search for an assignment of the variables of the problem  $p$    
of minimal valuation, less than  $\alpha_{init}$    
; and greater than or equal to  $\beta$    
by default,  $\alpha_{init} = \top$  et  $\beta = \bot$  let be  $\alpha =$  DFBB-VARIABLES(0,VARIABLES(p),  $\bot ,\alpha_{init},\beta)$  if  $\alpha = \alpha_{init}$  then return failure else return  $\alpha$    
DFBB-VARIABLES(A,V, $\alpha^{\prime},\alpha ,\beta)$    
; A is the current assignment   
;  $V$  is the set of uninstantiated variables   
;  $\alpha^\prime$  is the valuation of the current assignment if  $V = \emptyset$  then return  $\alpha^{\prime}$  else let be  $v =$  VARIABLE-CHOICE(V) return DFBB-VARIABLEA,V,v,DMAIN(v),  $\alpha^{\prime},\alpha ,\beta)$    
DFBB-VARIABLEA,V,v,d,  $\alpha^{\prime},\alpha ,\beta)$  if  $d = \emptyset$  then return  $\alpha$  else let be val  $=$  VALUE-CHOICE(d) let be  $\alpha '' =$  DFBB-VALUE(A,V,v,val,  $\alpha^{\prime},\alpha ,\beta)$  if  $\alpha '' = \beta$  then return  $\beta$  else return DFBB-VARIABLEA,A,V,v,d⊥{val},  $\alpha^{\prime},\alpha^{\prime \prime},\beta)$    
DFBB-VALUe(A,V,v,val,  $\alpha^{\prime},\alpha ,\beta)$  let  $\alpha '' =$  VALUATION(A,v,val,  $\alpha ^ { \prime }$  ） if  $\alpha ''\succeq \alpha$  then return  $\alpha$  else return DFBB-VARIABLES(AU{v,val},V⊥{v},  $\alpha ''$  ,α,β)
```

Figure 1: Depth First Branch and Bound

This algorithm presents the following advantages :

- it only requires a limited space (linear w.r.t. the number of variables);

- as soon as a first assignment with a valuation less than  $\alpha_{init}$  is found, the algorithm behaves like an anytime algorithm: if interrupted, the best solution found can be returned and its quality cannot but improve over time.

The main problem is that a depth first search can easily be stuck into a portion of the search space where no optimal assignment exists, because of the first choices made during the search.

# 2.1.2 Pseudo Dynamic Search

The second algorithm is a generalization to the VCSP framework, of a Spot5 specific algorithm developed by D. Blumstein and J.C. Agnèsé for finding optimal solutions. As it can be seen as an hybridization of Dynamic Programming and Branch and Bound, we called it Pseudo Dynamic Search.

Given a problem  $p$  with  $n$  variables; the method, which assumes a static variable ordering, consists in performing  $n$  searches, each one solving, with the standard Depth First Branch and Bound algorithm, a subproblem of  $p$  limited to a subset of the variables. The  $i^{th}$  problem is limited to the  $i$  last variables. Each problem is solved by using the same variable ordering, i.e., from variable  $(n \perp i + 1)$  to  $n$ . The optimal valuation is recorded as well as the corresponding assignment. They will be used when solving the next problems, to improve the valuation of the partial assignments and thus to provide better cuts. Figure 2 describes this algorithm.

```txt
PDS  $(p,\alpha_{init})$  ；search for an assignment of the variables of the problem  $p$  ；with a minimal valuation less than  $\alpha_{init}$  ；by default,  $\alpha_{init} = \top$  let be  $\alpha = \mathrm{PDS - VARIABL ES}(\emptyset ,\mathrm{VARIABL ES}(p),\alpha_{init},\bot)$  if  $\alpha = \alpha_{init}$  then return failure else return  $\alpha$  PDS-VARIABLES(V,V',  $\alpha_{init},\alpha$  ）  $V\cup V^{\prime} =$  VARIABLES(p) ；  $\alpha$  is the optimal valuation of the problem restricted to ；the variables in  $V$  ，found in the previous search if  $V^{\prime} = \emptyset$  then return  $\alpha$  else let be  $v =$  FIRST-VARIABLE(V) let be  $\alpha^{\prime} =$  DFBB-VARIABLES(0,VU{v},⊥,  $\alpha_{init},\alpha$  ） if  $\alpha^{\prime} = \alpha_{init}$  then return  $\alpha_{init}$  else return PDS-VARIABLES(VU{v},V'⊥{v},  $\alpha_{init},\alpha^{\prime}$
```

Figure 2: Pseudo Dynamic Search

This method, which can be surprising since it multiplies by  $n$  the number of searches, has proved to be very efficient. The main explanation is in the quality of the valuation of the partial assignments provided by previous searches. The loss of the anytime property of the standard Depth First Branch and Bound (one must wait up to the  $n^{th}$  search to get a solution) is however an important drawback.

# 2.2 Valuation of a partial assignment

The efficiency of methods based on Branch and Bound mainly depends on the way partial assignments are evaluated. This evaluation must be optimistic and as realistic as possible.

# 2.2.1 Backward Checking

Within the VCSP framework, the first way to evaluate a partial assignment is to aggregate the valuations of the constraints instantiated by  $A$  and not satisfied (a constraint is said instantiated when all the

variables linked by it are instantiated) :

$$
v p _ {b c} (A) = \otimes_ {c \in C, c \text {i n s t a n t i a t e d a n d n o t s a t i s f i e d b y A}} [ \varphi (c) ]
$$

This evaluation is optimistic, since it only takes into account the constraints instantiated by  $A$ , but it is not very realistic when the number of uninstANTIATED constraints is high, i.e at the beginning of search.

# 2.2.2 Forward Checking

A way to improve this evaluation is not only to consider the instantiated constraints, but also the constraints for which all the variables but one are instantiated by  $A$  (for these ones, we have obviously to consider all the possible instantiations of the uninstantiaded variable):

$$
v p _ {f c} (A) = v p _ {b c} (A) \otimes [ \otimes_ {v \in V, v u n i n s t a n t i a t e d} [ \min _ {v a l \in d o m a i n (v)} [ v p _ {b c} (A \cup \{v a l \}) \perp v p _ {b c} (A) ] ] ]
$$

This evaluation is still optimistic. It is more realistic than Backward Checking ( $\forall A, v p_{fc}(A) \geq v p_{bc}(A)$ ). However, it remains not very realistic at the beginning of the search. Forward Checking is also more costly in terms of number of constraint checks at each node, but it is often verified that this cost is counterbalanced by a more important pruning.

# 2.2.3 Pseudo Dynamic Search

When the Pseudo Dynamic Search strategy is used, another valuation of the partial assignments can be performed, which takes into account the constraints linking instantiated variables and the ones linking uninstantiated variables, but ignores the ones linking instantiated and uninstANTIated variables. Let  $V$  be the set of variables uninstANTIATED by  $A$  and  $v_{opt}(V)$  be the optimal valuation of the problem limited to these variables (known from previous searches):

$$
v p _ {p d s} (A) = v p _ {b c} (A) \otimes v _ {o p t} (V)
$$

This valuation is optimistic, since it does not take into account the constraints linking instantiated and uninstANTIATED variables. It is more realistic than the previous two ones from the beginning of the search.

If we try to compare this valuation with the one corresponding to Forward Checking, none of those is systematically more realistic than the other. So both can be combined by using the max operator:

$$
v p _ {p d s - f c} (A) = m a x (v p _ {p d s} (A), v p _ {f c} (A))
$$

# 2.3 Heuristics

Heuristics play a great role in this kind of search. They can be generic or specific (application dependent), static or dynamic. They can be used at three levels:

- Variable ordering : the first fail principle is used; it consists in first instantiating variables which will sooner allow to detect a failure (no possible extension with a valuation less than the current bound  $\alpha$ ); some examples of generic heuristics : first choose variables with the smallest domain or which maximize the number of constraints to check or the minimal valuation increase (when Forward Checking is used); some examples of specific ones : first choose variables with the highest weight or select them according to the chronological order of the corresponding photographs.

- Value Ordering: the best first principle is used; it consists in first choosing values which will a priori lead to a solution; examples of generic heuristics are few: first choose values which minimize the valuation increase (when Forward Checking is used); some examples of specific heuristics: last choose the special value 0, first choose the middle instrument for mono photographs (because stereo photographs use the others) or select values to balance the load over the three instruments;

- Constraint Ordering: the order in which constraints are checked also follows the first fail principle; it can be based on the constraint satisfiability (first constraints with the lowest satisfiability) or on the constraint valuation (first constraints with the highest valuation); but the role of this kind of heuristic is only to try to reduce the number of constraint checks; unlike variable and value orderings, it cannot reduce the size of the tree search.

From our experiments, it can be quoted that:

- search is more sensitive to variable ordering than to value ordering: due to the small size of the domains, value ordering has little impact on search and last considering the special value 0 is sufficient;

- the most interesting variable orderings are application dependent: choosing first variables with the highest weight for the standard Depth First Branch and Bound or using the chronological order for the Pseudo Dynamic Search to exploit the structure of the constraint graph.

# 3 APPROXIMATE METHODS

This section presents methods which aim at providing good solutions, but cannot prove optimality. Originally, they have been developed by the CNES team and are dedicated to the Spot5 scheduling problem. Although they have been defined and implemented for this specific application, they are described within the VCSP framework to keep an unified presentation and because their generalization to VCSP is quite obvious.

# 3.1 Greedy Search

This algorithm works in two phases :

1. the first phase deals with the computation of a feasible solution: trials are first heuristically sorted, then a solution is built by trying to insert each trial in the current solution and rejecting it if it is impossible;

2. the solution, result of the first phase, is then improved by a perturbation method based on an iterative inhibition of the selected trials; for each selected trial, it consists in rejecting it and computing a new schedule from this point (the portion of schedule from the beginning up to the trial being kept) if a better solution is found, the trial is definitively rejected and the current solution uptaded; else, it is definitively selected.

Figure 3 presents the translation within the VCSP framework of this algorithm. The procedure FEASIBLE, not detailed, makes the necessary constraint checks to decide if adding the new instantiation  $\{v = j\}$  to the current assignment  $A$  is possible or not.

This algorithm is a example of combination of greedy search (first phase) and limited local search (second phase). The quality of the solutions found greatly depends on the sort performed at the beginning of the first phase. In the SPOT5 problem framework, this sort uses some of the following criteria, whose aim is to maximize the solution quality and to limit the conflicts:

1. first trials with a high weight;

2. mono trials before stereo trials (because a stereo trial requires twice more resources);

3. mono trials preferably affected to the middle instrument (because stereo trials are realized with the front and rear instruments);

4. first trials with a low data flow (to limit conflicts due to data flow and memory requirements);

5. first trials in conflict with a little number of other trials;

6. chronological order.

In our implementation, several initial schedules (up to five) are computed, by using different trial orderings. Each of them uses as the most important criterion the trial weight and as the least important one the chronological order. They only differ by the intermediate criteria, as shown in table 5. A first version, called Greedy Algorithm, performs the improvement phase on the best schedule produced during the first phase. A second version, called Multi Greedy Algorithm, performs it on all of them. It is obviously more time consuming than the first one, but it sometimes succeeds to produce better quality solutions.

```txt
BUILD-SOLUTION(A,V) for each variable  $v\in V$  Free  $= \text{true},i = 1$  while Free  $j = i^{th}$  value of domain(v) if FEASIBLE(A,v,j) then  $A = A\cup \{v = j\} ,Free = \text{false}$  else  $i = i + 1$  end while end for return A   
IMPROVE-SOLUTION(A,V) Part  $= \emptyset$  Best  $= A$  Free  $= V$  for each instantiation  $\{v = j\} \in A$  if  $j\neq 0$  then New  $=$  BUILD-SOLUTION(Part U  $\{v = 0\} ,V)$  if valuation(New)  $>$  valuation(Best) then Best  $= \mathsf{New}$ $k = 0$  else  $k = j$  else  $k = 0$  end if Free  $= \text{Free}\bot \{v\}$  Part  $= \text{Part}\cup \{v = k\}$  end for return Best
```

Figure 3: Greedy Search

<table><tr><td>Ordering</td><td>Criteria</td></tr><tr><td>1</td><td>[1, 6]</td></tr><tr><td>2</td><td>[1, 2, 6]</td></tr><tr><td>3</td><td>[1, 4, 6]</td></tr><tr><td>4</td><td>[1, 3, 6]</td></tr><tr><td>5</td><td>[1, 5, 6]</td></tr></table>

Table 5: Combinations of criteria used by the different orderings

# 3.2 Tabu search

Tabu search (see [5] for a detailed presentation), like any other local search method, can certainly be well introduced by using a geometric analogy of the search process. For that, each assignment of all the problem variables can be considered as a point in an  $n$ -dimensional space (the search space,  $n$  being the number of variables). Each point  $p$  has a valuation  $v(p)$  characterizing the quality of the corresponding solution  $(v(p) = +\infty$  means that  $p$  does not represent a feasible solution). The search process can then be viewed as moving process from point to point, trying to find points with a better valuation than the best point encountered so far.

A initial point can always be found : either the void solution (all the variables instantiated to the value 0), or any good solution as the one provided for example by the greedy algorithm.

Completely arbitrary moves (changing several variable instantiations at the same time) are not considered, but only the simplest ones (changing one variable instantiation). More precisely, we only consider two types of moves:

- to add a photograph to the current solution : instantiation changed from 0 to  $i$  ;

- to suppress a photograph from the current solution : instantiation changed from  $i$  to 0.

This limitation makes that many points in the search space cannot be directly reached from a given point  $p$ . The set of points that can be directly reached from  $p$  via feasible moves is called its neighborhood  $n(p)$ .

A move from a point  $p$  to a point  $p'$  can be given a value  $\Delta_v(move(p, p')) = v(p') \perp v(p)$ . Basically the new point selected from the point  $p$  is the one in  $n(p)$  which has the best value. Note that, when no point better than  $p$  exists in  $n(p)$ , a worse one can be selected. This allows the search to escape from local optima. Endless cycling is avoided by forbidding the reverse move, which becomes tabu, for a certain time after this move (where the name of the method comes from). In some circumstances, this tabu restriction can be overridden and a tabu move selected. The main example of such an aspiration is when a tabu move leads to a better point than the best one found so far.

To keep a history of the search, the following data are recorded, for each photograph :

- the iteration at which it has been inserted or removed from a solution (short term memory);

- the number of tried insertions (mid term memory).

The short term memory is used to implement the tabu restriction, the mid term one to penalize the insertion of very frequently inserted photographs and to force a diversification of the search, guiding it into yet unexplored area of the space. But this penalization is only applied when the search is in a phase where the solution quality is decreasing.

Besides, solutions with a very good valuation (elite solutions) are recorded as they are found in a long term memory. Only elite solutions sufficiently different from the previously recorded ones are stored. This memory is used to reinforce the search in regions of the space which have provided some good solutions in the past. At a regular frequency (see algorithm TABU-SEARCH), the last elite solution found is restored, the short and mid term memories are reset and an entirely new search starts from this point.

Figure 4 presents some of the procedures used in the Tabu Search algorithm. The recording of solutions is made within the procedure APPLY-MOVE, which is not described here.

Some remarks :

- this description is a strong simplification of the algorithms really implemented; for example, the procedure SELECT-MOVE does not really consider at each iteration all the moves in  $n(p)$ , but only a limited subset of them;

- the duration, during which a move is  $tabu$ , is not fixed, but computed by generating a random number within a given range, dependent of the size of the problem: for this specific application, ranges of [3,5] for problems of size less than 500 trials and [7,10] for problems of size greater than 500 trials have been found adequate;

- usual strategies in the framework of tabu search, like path relinking and strategic oscillation, have not yet been implemented, despite the fact they may improve the efficiency of the search.

```txt
SELECT-MOVE  $(p,i,c)$    
;returns the best move from the point  $p$  at the iteration i   
;  $c = 0$  : no penalty applied,  $c = 1$  : penalty applied   
bestval  $= \bot \infty$ $v = v(p)$    
for each move  $\in n(p)$  do   
if FEASIBLE(move)   
then  $\delta = \Delta_v(move)$    
if TABU(move) then if  $v + \delta \leq best_{val}$  then  $\delta = \bot \infty$  ;forallenmove else  $\delta = \delta +\mathrm{PENALTY}(c,i,move)$  if  $v + \delta >best_{val}$  then bestmove  $=$  move,bestval  $= v + \delta$    
end for   
return bestmove
```

```matlab
DIVERSIFICATION  $(p,i_{max})$    
; search for  $i_{max}$  iterations from the point  $p$ $i = 0$    
repeat ; search without penalty move  $=$  SELECT-MOVE  $(p,i,0)$ $p =$  APPLY-MOVE  $(p,i,\text{move})$ $i = i + 1$  until (no improvement for the  $i_{max} / 100$  last iterations)   
while  $i <   i_{max}$  ; alternate search with and without penalty applied move  $=$  SELECT-MOVE  $(p,i,0)$  while  $\Delta_v(move)\leq 0$  ; search for a local optimum without penalty  $p =$  APPLY-MOVE  $(p,i,\text{move})$ $i = i + 1$  move  $=$  SELECT-MOVE  $(p,i,0)$  end while   
while  $\Delta_v(move) > 0$  ; search for a local optimum with penalty  $p =$  APPLY-MOVE  $(p,i,\text{move})$ $i = i + 1$  move  $=$  SELECT-MOVE  $(p,i,1)$  end while   
end while
```

```txt
TABU-SEARCH  $(V,i_{max})$    
;main procedure  $p =$  INIT-SOLUTION  $(V)$ $i = 0$  while  $i\leq i_{max}$  DIVERSIFICATION  $(p,i_{max} / 10)$ $p =$  RESTORE-ELITE-SOLUTION RESET-SHORT-MID-TERM-MEMORY end while
```

Figure 4:Tabu Search

# 4 RESULTS

# 4.1 Data

The set of data provided by CNES [6] involves 498 scheduling problems. They correspond to :

- 384 problems, called without limitation, corresponding to scheduling problems limited to one orbit where the recording capacity constraint is ignored:

- 362 basic problems generated with the simulator LOSICORDOF, numbered from 1 to 362;

- 13 problems, built from the biggest of the 362 previous ones (the number 11), by reducing the number of photographs, numbered from 401 to 413;

- 9 problems, built from the same problem, by reducing the number of conflicts between photographs, numbered from 501 to 509;

- 114 problems, called with limitation, corresponding to problems over several consecutive orbits, between two dumping of data, where the recording capacity constraint cannot be ignored:

- 101 basic problems generated with the simulator, numbered from 1000 to 1101;

- 6 problems, built from the biggest of the 101 previous ones (the number 1021), by reducing the number of photographs, numbered from 1401 to 1406;

- 7 problems, built from the same problem, by reducing the number of conflicts between photographs, numbered from 1501 to 1507.

Because of the repartition of the photographs on the orbit, some problems can be decomposed into independent subproblems. This property is used to solve the subproblems in sequence.

# 4.2 Partial results

To experiment and compare the different methods, 20 representative problems have been selected :

- 13 problems without limitation : 54, 29, 42, 28, 5, 404, 408, 412, 11, 503, 505, 507 et 509;

- 7 problems with limitation : 1401, 1403, 1405, 1021, 1502, 1504 et 1506.

Tables 6 and 7 present the results obtained on these problems by the four following methods :

- DFBB: the standard Depth First Branch and Bound, with a time limitation of 600 seconds per subproblem;

-  $PDS$ : the Pseudo Dynamic Search, without time limitation;

-  $GR$ : the Multi Greedy Search;

- TS: the Tabu Search.

$Pb$  is the problem number and  $Nv$  is the corresponding number of problem variables (number of photographs). For each pair problem-method, the first number is the best solution quality (the sum of the weights of the selected photographs; * indicates that optimality has been proved) and the second number is the cpu time in seconds.

Results in column DFBB and the result for problem 5 in column PDS correspond to an implementation of the corresponding algorithms in Lucid Common Lisp 4.1.1 on a Sparc 1000 workstation, other results to an implementation in Fortran 77 running on a Sparc 20/50 workstation.

<table><tr><td>Pb</td><td>Nv</td><td colspan="2">DFBB</td><td colspan="2">PDS</td><td colspan="2">GR</td><td colspan="2">TS</td></tr><tr><td>54</td><td>67</td><td>70*</td><td>32</td><td>70*</td><td>3</td><td>69</td><td>4</td><td>70</td><td>253</td></tr><tr><td>29</td><td>82</td><td>12032*</td><td>12</td><td>12032*</td><td>1</td><td>12032</td><td>1</td><td>12032</td><td>1</td></tr><tr><td>42</td><td>190</td><td>104067</td><td>1201</td><td>108067*</td><td>14</td><td>108067</td><td>13</td><td>108067</td><td>634</td></tr><tr><td>28</td><td>230</td><td>53053</td><td>612</td><td>56053*</td><td>415</td><td>50053</td><td>4</td><td>56053</td><td>1416</td></tr><tr><td>5</td><td>309</td><td>112</td><td>1213</td><td>114*</td><td>1702</td><td>114</td><td>43</td><td>114</td><td>293</td></tr><tr><td>404</td><td>100</td><td>48</td><td>600</td><td>49*</td><td>2</td><td>47</td><td>3</td><td>49</td><td>237</td></tr><tr><td>408</td><td>200</td><td>3076</td><td>603</td><td>3082*</td><td>184</td><td>3078</td><td>19</td><td>3082</td><td>279</td></tr><tr><td>412</td><td>300</td><td>15078</td><td>611</td><td>16102*</td><td>255</td><td>16097</td><td>43</td><td>16101</td><td>1166</td></tr><tr><td>11</td><td>364</td><td>21096</td><td>646</td><td>22120*</td><td>419</td><td>22112</td><td>68</td><td>22116</td><td>1433</td></tr><tr><td>503</td><td>143</td><td>8094</td><td>611</td><td>9096*</td><td>38</td><td>9093</td><td>22</td><td>9096</td><td>272</td></tr><tr><td>505</td><td>240</td><td>12088</td><td>603</td><td>13100*</td><td>108</td><td>12102</td><td>39</td><td>13100</td><td>1269</td></tr><tr><td>507</td><td>311</td><td>13101</td><td>620</td><td>15137*</td><td>303</td><td>15129</td><td>54</td><td>15136</td><td>1385</td></tr><tr><td>509</td><td>348</td><td>19104</td><td>638</td><td>19125*</td><td>382</td><td>19116</td><td>63</td><td>19123</td><td>1384</td></tr></table>


Table 6: Without limitation problems


<table><tr><td>Pb</td><td>Nv</td><td colspan="2">DFBB</td><td colspan="2">PDS</td><td colspan="2">GR</td><td colspan="2">TS</td></tr><tr><td>1401</td><td>488</td><td>165058</td><td>648</td><td>-</td><td>-</td><td>167060</td><td>93</td><td>174058</td><td>846</td></tr><tr><td>1403</td><td>665</td><td>165133</td><td>1867</td><td>-</td><td>-</td><td>167143</td><td>279</td><td>174137</td><td>1324</td></tr><tr><td>1405</td><td>855</td><td>165154</td><td>1342</td><td>-</td><td>-</td><td>167182</td><td>692</td><td>174174</td><td>1574</td></tr><tr><td>1021</td><td>1057</td><td>165221</td><td>1988</td><td>-</td><td>-</td><td>167249</td><td>1241</td><td>174238</td><td>2197</td></tr><tr><td>1502</td><td>209</td><td>60155</td><td>601</td><td>61158*</td><td>13</td><td>61158</td><td>60</td><td>61158</td><td>454</td></tr><tr><td>1504</td><td>605</td><td>115228</td><td>1808</td><td>-</td><td>-</td><td>120239</td><td>405</td><td>124238</td><td>1011</td></tr><tr><td>1506</td><td>940</td><td>153226</td><td>1906</td><td>-</td><td>-</td><td>163244</td><td>897</td><td>165244</td><td>1945</td></tr></table>

Table 7: With limitation problems

# Some comments :

- Concerning without limitation problems :

-  $PDS$  produces an optimal solution and proves its optimality on all the problems;

-  $DFBB$  does the same thing on only two of them; on the others, the produced solutions are not very good;

-  $GR$  is the fastest algorithm; it seldom produces an optimal solution, but the produced solutions are often better than the ones produced by DFBB;

-  $TS$  produces optimal or near optimal solutions on all the problems, obviously without any proof of optimality; but it often takes more time than  $PDS$ .

- Concerning with limitation problems:

-  $PDS$  terminates on only one problem;

-  $TS$  provides the best solutions and  $DFBB$  the worse ones.

# 4.3 Global results

Results obtained on the whole data set show the efficiency of both Pseudo Dynamic Search and Tabu Search.

# 4.3.1 Efficiency of Pseudo Dynamic Search

For optimality proof, the Pseudo Dynamic Search, outranks the standard Depth First Branch and Bound. Its performances are summarized in table 8 w.r.t. the size of the problem: the class  $i-j$  is the set of

<table><tr><td>Class</td><td>Npb</td><td>Nopt</td><td>%</td></tr><tr><td>1-100</td><td>315</td><td>313</td><td>99.4</td></tr><tr><td>101-200</td><td>74</td><td>67</td><td>90.5</td></tr><tr><td>201-300</td><td>47</td><td>29</td><td>61.7</td></tr><tr><td>301-400</td><td>24</td><td>18</td><td>75.0</td></tr><tr><td>401-500</td><td>13</td><td>0</td><td>0.0</td></tr><tr><td>501-600</td><td>6</td><td>0</td><td>0.0</td></tr><tr><td>601-700</td><td>5</td><td>0</td><td>0.0</td></tr><tr><td>701-800</td><td>3</td><td>0</td><td>0.0</td></tr><tr><td>801-900</td><td>4</td><td>0</td><td>0.0</td></tr><tr><td>901-1000</td><td>4</td><td>0</td><td>0.0</td></tr><tr><td>1001-1100</td><td>3</td><td>0</td><td>0.0</td></tr><tr><td>Total</td><td>498</td><td>427</td><td>85.7</td></tr></table>

Table 8: Efficiency of Pseudo Dynamic Search

problems with a number of variables  $Nv$  such that  $i \leq Nv \leq j$ ,  $N_{p_b}$  is the number of problems in the class and  $N_{opt}$  the number of problems in the class optimally solved by  $PDS$ .

Globally, PDS solves optimally  $85.7\%$  of the problems (90.8% for the subset without limitation, 68.4% on the subset with limitation). But, when problems become large ( $Nv > 400$ ), efficiency falls. It should be quoted that the main reason is not the number of variables itself, but the presence of the high arity recording capacity constraint (large problems correspond to those where the recording capacity limitation is present).

# 4.3.2 Efficiency of Tabu search

Starting from the solution provided by the Greedy algorithm, the Tabu Search generally succeeds to substantially improve it: on  $32\%$  of the without limitation problems, on  $56\%$  of the with limitation problems. It often provides optimal solutions or one of the best known solutions: on  $90\%$  of the without limitation and with limitation problems (the best known solutions are, either the optimal ones produced by exact methods, like PDS, or the ones produced by other versions of TS, since several versions of TS, corresponding to different parameter settings, may provide different solutions).

# 5 CONCLUSION

Exact methods, like Depth First Branch and Bound or Pseudo Dynamic Search, have the advantage to provide optimal solutions and to prove this optimality, when no time limit is set. They succeed within a reasonable time on small and medium size problems, but fail on large size ones or in presence of high arity constraints. When they fail, the systematic order they use to explore the search space prevents them to produce very good quality solutions.

Approximate methods, like Greedy Search or Tabu Search, have the advantage to provide within a limited time good quality solutions, thanks to their opportunistic way to explore the search space. But they have the disadvantage to provide no guarantee about this quality and sometimes to lose a lot of time to try to improve optimal solutions. They should be used when it is very likely, according to the problem characteristics (number of variables, domain sizes, constraint arities ...), that the exact ones will fail.

But if this competition between exact and inexact methods is technically exciting, it might be very fruitful, from a practical point of view, to consider a cooperation between them: for example, to use an efficient exact method and an efficient inexact one in parallel on the same problem and to use partial results obtained by each of them to guide or cut the search of the other one.

# References



[1] J.C. Agnès. Ordonnancement SPOT5: Définition du problème simplifié de l'ordonnancement des prises de vue de SPOT5 pour l'action de R&D Intersolve. Technical Report S5-NT-0-379-CN, -94-CT/TI/MS/MN/419, CNES, 1994.





[2] T. Schiex. Préférences et Incertitudes dans les Problèmes de Satisfaction de Contraîntes. Technical Report 2/7899 DERA, CERT, 1994.





[3] T. Schiex, H. Fargier, and G. Verfaillie. Valued Constraint Satisfaction Problems : Hard and Easy Problems. In Proc. of IJCAI-95, Montréal, Canada, 1995.





[4] G. Verfaillie and E. Bensana. Evaluation d'algorithmes sur le problème de programmation journalière des prises de vue du satellite d'observation SPOT5 (Etude CNES INTERSOLVE, Lot 1). Technical Report 1/3544/DERI, CERT, 1995.





[5] F. Glover and M. Laguna. Modern Heuristic Techniques for Combinatorial Problems, chapter Tabu Search. 1992.





[6] J.C. Agnès. Ordonnancement SPOT5: Fourniture de fichiers de données pour l'action de R&D Intersolve. Technical Report -94-CT/TI/MS/MN/467, CNES, 1994.

