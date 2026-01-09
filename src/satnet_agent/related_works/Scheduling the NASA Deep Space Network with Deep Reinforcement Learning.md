# Scheduling the NASA Deep Space Network with Deep Reinforcement Learning

Edwin Goh, Hamsa Shwetha Venkataram, Mark Hoffmann, Mark Johnston, Brian Wilson  
Jet Propulsion Laboratory, California Institute of Technology  
4800 Oak Grove Dr., Pasadena, CA 91109  
edwin.y.goh@jpl.nasa.gov

Abstract—With three complexes spread evenly across the Earth, NASA's Deep Space Network (DSN) is the primary means of communications as well as a significant scientific instrument for dozens of active missions around the world. A rapidly rising number of spacecraft and increasingly complex scientific instruments with higher bandwidth requirements have resulted in demand that exceeds the network's capacity across its 12 antennae. The existing DSN scheduling process operates on a rolling weekly basis and is time-consuming; for a given week, generation of the final baseline schedule of spacecraft tracking passes takes roughly 5 months from the initial requirements submission deadline, with several weeks of peer-to-peer negotiations in between. This paper proposes a deep reinforcement learning (RL) approach to generate candidate DSN schedules from mission requests and spacecraft ephemeris data with demonstrated capability to address real-world operational constraints. A deep RL agent is developed that takes mission requests for a given week as input, and interacts with a DSN scheduling environment to allocate tracks such that its reward signal is maximized. A comparison is made between an agent trained using Proximal Policy Optimization and its random, untrained counterpart. The results represent a proof-of-concept that, given a well-shaped reward signal, a deep RL agent can learn the complex heuristics used by experts to schedule the DSN. A trained agent can potentially be used to generate candidate schedules to bootstrap the scheduling process and thus reduce the turnaround cycle for DSN scheduling.

# TABLE OF CONTENTS

1 INTRODUCTION 1

2 RELATED WORK 2

3 PROBLEM FORMULATION AND DESIGN 2

4 RESULTS AND DISCUSSION 5

5 CONCLUSIONS AND FUTURE WORK 7

REFERENCES 7

# 1. INTRODUCTION

As humankind progresses towards groundbreaking space explorations ranging from searching for signs of extraterrestrial life by roving on the red planet [1] to understanding the composition interstellar space [2], communicating with the spacecraft to exchange engineering and scientific data becomes increasingly critical. The resurgence of manned exploration efforts to the Moon and Mars further elevates the importance of communications to one of guaranteeing the safety of hu

©2021 IEEE. Personal use of this material is permitted. Permission from IEEE must be obtained for all other uses, in any current or future media, including reprinting/republishing this material for advertising or promotional purposes, creating new collective works, for resale or redistribution to servers or lists, or reuse of any copyrighted component of this work in other works.

manity's explorers. The NASA Deep Space Network, managed and operated by the Jet Propulsion Laboratory (JPL), is an international network of three facilities strategically located around the world to support constant observation of spacecraft launched as part of various interplanetary (and indeed, interstellar) missions. As one of the largest and the most sensitive telecommunications systems in the world, DSN also supports Earth-orbiting missions along with radio astronomy, radar astronomy, and related solar system observations.

With 12 operational antennas (as of 2019) spread across three locations — Goldstone, USA, Madrid, Spain and Canberra, Australia — DSN has served roughly 150 missions for spacecraft communications, and at the time of writing is very near its full capacity. For some weeks, the system is already over-subscribed by the various missions, especially those that cluster in the same portion of the sky [3]. In addition, the recently-launched Mars 2020 mission adds additional requirements with eight cameras and sophisticated instruments to search for biological evidence of life on the surface. The combined factors of more frequent missions and increased demand for higher-fidelity data operations are expected to significantly increase the load on the DSN. To address the issues of over-subscription, budget constraints and system downtimes, there is urgent need (and thus much ongoing research) to improve the DSN scheduling process such that "better" candidate schedules (e.g., with more tracks placed, less conflicts, fairer distribution of tracking time across missions, etc.) can be generated in a much shorter turnaround time. This implies a need to search the solution space for good candidate schedules with such expediency and completeness that exceeds human capabilities, as well as a need to alleviate the bottleneck imposed by the peer-to-peer negotiations process.

Real-world optimization tasks typically have a large number of operational or physical constraints. When solving such problems with conventional operations research techniques, great care is taken to formulate the problem so as to avoid the "curse of dimensionality" in which the problem becomes exponentially complex and computationally intractable. The DSN scheduling problem indeed imposes numerous resource allocation constraints due to the wide range of spacecraft orbits, mission requirements, and operational considerations (e.g., hand-off between DSN complexes as the Earth rotates relative to the spacecraft). Deep reinforcement learning (deep RL) is a recent alternative to these conventional approaches that has shown promise in solving complex tasks that are typically considered to rely heavily upon intuition or creativity

[4,5]. A sub-domain in the field of Artificial Intelligence (AI), deep RL is a combination of reinforcement learning [6] and deep learning. Deep RL is fundamentally represented as a Markov Decision Process (MDP) and typically consists of an agent that interacts with an environment by observing rewards for actions that it takes, as shown in Fig. 1.

![image](https://cdn-mineru.openxlab.org.cn/result/2026-01-02/01e9d79a-e24b-4eea-b03f-48865280d466/5da2400f91c3902454418b7cf96bf769b3a75f75ca9d27741fc40f125a00d22a.jpg)



Figure 1. Deep RL Canonical Diagram


Recent work on the application of deep RL to scheduling problems in cloud computing resources [7] and wireless networks [8] has demonstrated the capability of these algorithms to learn complex rules and strategies required to accomplish such tasks. It has been shown to perform comparably if not better than conventional metaheuristic optimization and search methods on classical operations research problems [9]. There have also been multiple instances where deep RL was successfully applied to NASA use cases [10-12]. With regards to JPL, the appealing aspects of this approach are as follows:

- Upfront investment of training an agent, however high in terms of initial resource requirements, is amortized over future problem sets (weeks) with near real-time inference, which can be performed using consumer hardware. This precludes running classical optimization solvers or training agents from scratch for every scheduling cycle.

- Potential infusion into various other ongoing areas of research such as job shop scheduling [10] and similar use cases at JPL, as well as applications in the public domain.

# Contributions

In this paper, we propose a policy optimization based scheduling approach to effectively generate de-conflicted candidate schedules for a given week using mission requests, antenna availability and other constraints as inputs. The purpose of this solution is threefold:

- Reduce scheduling turnaround time from a few months to few days.

- Increase antenna utilization and thus accommodate more missions.

- Minimize the unsatisfied time fraction experienced by each user, i.e., improve "fairness" of track allocations across missions.

# 2. RELATED WORK

Deep Space Network schedules are typically generated a year into the future with allocations to the minute, and are performed manually, one week at a time [13]. Requested tracks are 1 to 8 hours long and are to be allocated in a view period (VP), defined as the period of time in which the spacecraft is visible to one or more antennas. In addition to the set of legal view periods for a given mission, some of the major constraints in DSN scheduling include quantization (whether scheduled activities are to occur on 1-minute or 5-minute constraints), sufficient separation of contacts (so that onboard data capacity is not exceeded), duration flexibility (reduction or extension of tracking time) and splitting of requests into multiple tracks [14]. Ongoing work seeks to further incorporate the notion of user preferences and mission priorities into the scheduling algorithm such that lower preference requests can be omitted under overscription, thereby reducing the amount of peerto-peer negotiation when potentially high-priority tracks are omitted instead [15].

The complexity of the DSN scheduling problem is well-known to the DSN user community, and a large body of literature exists around its solution. Guillaume et al. [16] explored a formulation of the problem in terms of evolutionary techniques, and leveraged that formulation to generate a population of Pareto-optimal schedules under varying conflict conditions. More recently, Oller [17] and Alimo et al. [18] formulated the task as Mixed Integer Linear Programming (MILP) problems to develop scheduling systems (for the long-range and mid-range scheduling problems, respectively) that incorporate many of the DSN's operational and physical constraints. Hackett et al. [19] investigated a beacon-tone demand access scheduling approach, whereby spacecraft, rovers and landers themselves submit ad-hoc requests for tracking time, which are then scheduled in real-time. The authors found that the paradigm decreased the number of required tracks compared to the conventional "pre-allocated" approach. On the other hand, [20] propose multi-objective reinforcement learning cognitive engine using deep neural networks to provide orbit planning and optimization designers the capability to leverage this framework and request resources on-demand. The authors in their other work, talk about "demand access" wherein spacecraft, or rovers request track time on the network themselves using a beacon-tone system and obtain "on-the-fly" track time on shared-user block tracks.

# 3. PROBLEM FORMULATION AND DESIGN

# Input Datasets

The main dataset used in this work is a set of User Loading Profiles (ULPs) for Week 44 of 2016 (an oversubscribed week), which provides the following information for a given mission:

1) The number of tracks requested for that week

2) The set of requested antenna combinations for these tracks

3) The requested duration for these tracks

4) The minimum valid duration for each track (used for splitting tracks into multiple periods)

In order to assign requested tracks to a particular antenna combination during a given week, one needs a set of view periods during which the spacecraft is visible by the requested antenna(s). We use ephemeris data downloaded from JPL's Service Preparation Subsystem (SPS) to assemble, for a given spacecraft and the requested antennas, this set of view periods. This task is a challenge in and of itself because of the potential for multiple-antenna requests that require tracks to be placed on antenna arrays. Such requests necessitate, in addition to the need to identify view periods that overlap across all requested antennas, the need for practical constraints to be taken into account, e.g., minimum duration for the requests, additional setup and teardown times, etc.

Finally, scheduled maintenance is also taken into account to further constrain the problem. Maintenance data for each antenna is downloaded from SPS and used in the view period identification step to filter out view periods that overlap with maintenance periods for a given antenna.

The aforementioned input datasets and the overall steps taken to obtain a final problem set to be used in the formulation is shown in Fig. 2 below.

![image](https://cdn-mineru.openxlab.org.cn/result/2026-01-02/01e9d79a-e24b-4eea-b03f-48865280d466/5bc7f026e127efcb49a6f2654f50d8bc92ca9d16fbf90ecb01a9f82bb3cfb02e.jpg)



Figure 2. Flow chart illustrating main steps used to generate the problem set, Week 44, 2016 used in this paper.


# Model/Environment

This section provides details about the environment used to simulate/represent the DSN Scheduling problem. The environment is implemented according to the OpenAI Gym [21] API in order to maintain compatibility with widely used reinforcement learning libraries such as RLlib and stable-baselines.

The simulation is instantiated with the problem set generated using the pipeline shown in Fig. 2, as well as a dictionary of DSN antennas. Therefore, episodes in this simulation are centered around week problems. Such a formulation is well-aligned with the DSN scheduling process described in Sec. 2, which generates schedules on a per-week basis.

Each Antenna object, initialized with start and end bounds for a given week, maintains a list of tracks placed as well as a list of time periods (represented as tuples) that are still

available. Algorithm 1 details the general algorithm used in this environment to satisfy requests in the problem set.


Algorithm 1: DSN Scheduling Simulation


Data: week problem set (see Fig. 2)  
while  $n_{rem} > 0$  or  $n_{steps} < 2n_{requests}$  do  
choose a request to allocate;  
for antenna in requested antenna combinations do  
| find and keep only valid VPs;  
end  
allocate track on antenna with longest valid VP;  
if duration of VP > requested duration then randomly shorten VP to match requested duration;  
end  
calculate seconds allocated;  
return reward and observation;  
end

As seen in the simulation steps detailed in Algorithm 1, Antenna objects provide the capability to process the set of valid view periods identified in Fig. 2 according to the antenna's availability and output a set of view periods that do not overlap with existing tracks already placed on that antenna. For multi-antenna requests, these available view periods for each antenna in the array are then passed through an overlap checker to find the overlapping ranges.

For the view periods that are available, the antenna provides utilities to check whether a view period is valid based on DSN-specific heuristics and rules. For the present work, a view period  $(t_1,t_2)$  with an associated setup/calibration duration  $d_{s}$  and breakdown duration  $d_{t}$  is considered valid if all the following conditions return true:

1)  $(t_{1} - d_{s}, t_{1})$  is available $^{2}$ , or if  $(t_{2} - t_{1}) \geq d_{\min} + d_{s} + d_{t}$

2)  $(t_2, t_2 + d_t)$  is available, or if  $(t_2 - t_1) \geq d_{\min} + d_s + d_t$

3)  $(t_2 - t_1) \geq d_{min}$ , where  $d_{min}$  is the minimum requested duration for this track

As we will discuss in the following sections, the present environment handles most of the "heavy-lifting" involved in actually placing tracks on a valid antenna, leaving the agent with only one responsibility — to choose the "best" request at any given time step. The simulation described thus far is a preliminary implementation. Constraints such as the splitting of a single request into tracks on multiple days or Multiple Spacecraft Per Antenna (MSPA) are important aspects of the DSN scheduling problem that require experience-guided human intuition and insight to fulfill. Being cognizant of this limitation, we intentionally implement this environment in a modular fashion such that subclasses with additional constraints can be easily defined in the future.

# State Space/Observation

At any given point in the simulation, the environment keeps track of:

i.e., does not overlap any of the tracks already placed on this antenna

- the distribution of remaining requested durations,

- the total outstanding requested hours for that week,

the number of unique missions with outstanding requests,

- the remaining number of requested tracks, and

the number of remaining free hours on each antenna.

In order to use the same observation space over multiple weeks, we specify a bound on the maximum number of requests (i.e., requested tracks) that are valid in any given week. For requests in the year 2016, a bound of 500 provided sufficient margin across all weeks. Thus 500 entries are defined for the distribution of remaining requested durations.

This state space of the environment is represented as a 1-D array that indicates the number of remaining unique missions, the number of remaining requests, the total remaining duration requested, as well as the remaining unallocated duration in each request.

# Action Space

There are multiple ways to enumerate the actions a reinforcement learning agent can take at each time step. An initial attempt specified the action space as a 2D binary grid whose rows represented the individual DSN antennas and the columns represented discretized time periods. When flattened/reshaped into a 1-D array, this resulted in a formidable action space of size  $2^{M \times K}$  where  $M$  is the number of DSN antennas and  $K$  is the number of time steps resulting from the discretization of the entire week by a given time step. Since such a large action space precludes efficient learning and makes the addition of DSN-defined constraints difficult, the current iteration of the action space for the DSN scheduling environment is intentionally simple — a single integer that defines which item in a request set the environment should allocate. Action masking is used in order to prevent the agent from choosing requests that have already been satisfied.

This implementation was developed with future enhancements in mind, eventually adding more responsibility to the agent such as choosing the resource combination to use for a particular request, and ultimately the specific time periods in which to schedule a given request. These decisions are hierarchical in nature and resemble the possible actions for each Dota agent in OpenAI Five [22], whereby an agent would for instance decide to attack, select a target to attack, and decide whether to offset the action in anticipation of the target unit's future position.

# Rewards

In the DSN scheduling environment, an agent is rewarded for an action if the chosen request index resulted in a track being scheduled. Here, the reward is given by,

$$
r _ {t} (s, a) = \frac {T _ {\text {a l l o c a t e d}}}{T _ {\text {r e q u e s t e d}}} \tag {1}
$$

where  $T_{allocated}$  is the total time scheduled across all antennas for this request and  $T_{requested}$  is the requested time allocation for the entire week.

At each time step, the reward signal is a scalar ranging from 0 (if the selected request index did not result in the allocation of any new tracking time) to 1 (if the environment was able to allocate the entire requested duration). As one can surmise, the theoretical maximum reward that can be achieved in an episode is the number of requests in that week.

# Training Algorithm

For this preliminary exploration, we use the Proximal Policy Optimization (PPO) algorithm [23] implemented in the RLlib reinforcement learning library [24]. While Schulman et al. demonstrated state-of-the-art performance with PPO on robotic locomotion/optimal control and Atari game playing, the algorithm has been shown to be feasible on stochastic optimization problems in operations research [9]. Furthermore, an RL agent trained on REINFORCE — another policy gradient algorithm similar to PPO — was shown to perform similarly and sometimes better than existing heuristics-based approaches for scheduling multi-resource clusters [25].

RLlib implements PPO in an actor-critic fashion. The actor is a typical policy network that maps states to actions, whereas the critic is a value network that predicts the state's value, i.e., the expected return for following a given trajectory starting from that state. For a batch of observations from the environment, the actor network predicts a distribution over the set of available actions. The training algorithm then samples a specific action from this distribution based on a given exploration strategy.

After an action is selected, the critic estimates the advantage  $A_{t}(s,a)$  as a function of the (temporal-difference) error  $\delta_{t}$  between the value function predicted by the network and the actual rewards returned by the environment. The error term is defined as

$$
\delta_ {t} = r _ {t} + \gamma V \left(s _ {t + 1}\right) - V \left(s _ {t}\right) \tag {2}
$$

where  $V$  is the critic's current model of the value function, and  $r_t$  is the ratio of action probabilities for the current state  $s_t$  under the current policy to the action probabilities for  $s_t$  under the old policy.

Thus for a given policy defined by the parameters  $\theta$ , the objective used in PPO is as follows,

$$
L ^ {P P O} (\theta) = \hat {\mathbf {E}} \left[ \min  \left(r _ {t} (\theta) A _ {t}, \operatorname {c l i p} \left(r _ {t} (\theta), 1 - \epsilon , 1 + \epsilon\right) A _ {t}\right) \right] \tag {3}
$$

where  $\epsilon$  is a hyperparameter proposed in [23] to clip  $r_t$  and thus prevent large policy updates that result in irrecoverable decreases in agent performance. Since the gradient of Eq. 3 is an estimator for the policy gradient, using this loss function as the objective to a stochastic gradient ascent problem is a surrogate for updating the policy to encourage good actions and weaken the tendency for actions that perform worse than expected.

While the results in [23] are obtained using an actor and critic that share the same layers, the neural architecture used in this work is one that has separate layers (and thus parameters) for both the policy and the value function. Throughout all

experiments, we use a fully-connected neural network architecture with 2 hidden layers of 256 neurons each. Based on the observation/state space defined above, the input layer is of size 518; the first three entries are the remaining number of hours, missions, and requests, the following set of 500 entries are the remaining number of hours to be scheduled for each request, and the final 15 entries are the remaining free hours on each antenna. We use a maximum number of requests of 500 to ensure that the same observation space can be used across multiple weeks.

![image](https://cdn-mineru.openxlab.org.cn/result/2026-01-02/01e9d79a-e24b-4eea-b03f-48865280d466/10de7cd51e545999d5f669fcabea00dcb77f2672a25d3eae1b059aa7bf2df03b.jpg)



Figure 3. Actor-critic network architecture used in this work. The left branch represents the actor network which maps observations to actions, whereas the right branch depicts the actor which learns to estimate the value of a given state.


# 4. RESULTS AND DISCUSSION

In this section, we first present details of the training process as well as the hyperparameters used. We then present preliminary solutions obtained using the formulation described above and compare those solutions with that of an agent taking random solutions. Solutions are presented for Week 44 of 2016. Excluding maintenance requests on the individual antennas, the DSN received a total of 286 requests for that week, which amounted to 1,770 hours to be allocated across DSN's antennas.

# Experimental Setup

Training was performed on a single Amazon EC2 instance with 4 GPUs and 32 CPUs, and the agent was trained for roughly  $\sim 10\mathrm{M}$  time steps using the RLlib framework. RLlib provides trainer and worker processes — the trainer is responsible for policy optimization by performing gradient ascent while workers run simulations on copies of the environment to collect experiences that are then returned to the trainer. RLlib is built on the Ray backend, which handles scaling and allocation of available resources to each worker.

PPO uses Stochastic Gradient Descent (SGD) algorithm, and in this experiment we set minibatch size to 128 and the number of epochs to 30 for optimizing the surrogate objective given in Eq. 3. While learning rate schedules can be defined in RLlib, the results presented here were trained using a

constant learning rate of 5e-5. The target Kullback-Leibler (KL) divergence [26] is set to 0.01 and the Generalized Advance Estimator (GAE) parameter,  $\lambda$ , is set to 1.0.  $\lambda$  is a bias-variance tradeoff parameter; higher values imply higher variance [27]. The discount factor or gamma parameter is set to 0.99, which gives more weighting on long-term rewards rather than immediate rewards. The clipping parameters for PPO policy and value function loss are set to RLLib defaults, and critic baseline is set to true for making use of GAE.

Fig. 4 shows the evolution of several key metrics from the training process. In Fig. 4a, mean and maximum rewards achieved by the policy across several 20 evaluation episodes are shown to increase in a stepwise fashion as the number of training episodes increases. One would expect the distribution of rewards to shift rightwards as the policy is progressively updated. Decreases in reward indicate periods where the agent doesn't exploit the best-available policy at the time, but instead explores other policies<sup>3</sup> to prevent itself from being trapped in local extrema. Furthermore, the average number of steps taken in each episode (Fig. 4b) is shown to decrease with training, indicating that the agent is capable of achieving better-performing schedules without spending additional steps to select requests that cannot be allocated. In other words, this may be an indication that the agent is learning to prioritize requests that can be allocated by the environment based on the availability of the antennas. Finally, Fig. 4c shows the evolution of entropy as training progresses. Entropy is an important indicator of whether there is variance in the actions taken by the policies being trained. The gradually decreasing entropy in Fig. 4c indicates that the PPO algorithm is converging on an optimal policy while maintaining its exploration policy.

# Random Agent Baseline

Due to complexities in the DSN scheduling process described in Section 1, the current iteration of the environment has yet to incorporate all necessary constraints and actions to allow for an "apples-to-apples" comparison between the present results and the actual schedule for week 44 of 2016. For example, the splitting of a single request into multiple tracks is a common outcome of the discussions that occur between mission planners and DSN schedulers. This allows for tracks to be fit into gaps that full requests otherwise would not, at the cost of increased overhead time due to setup and teardown.

Instead of comparing to historical data, we define the performance of a random agent<sup>4</sup> to be the baseline result. Recall that actions in this case are integers that represent the index of the request to schedule) and passing them into the environment. As seen in Fig. 5, a random agent without action masking chooses uniformly across the entire range of possible request indices (0-500).

3Recall that policies in this case are deep neural networks parameterized by  $\theta$

4A random agent is one that uniformly samples the action space at every time step of the environment.

![image](https://cdn-mineru.openxlab.org.cn/result/2026-01-02/01e9d79a-e24b-4eea-b03f-48865280d466/433f40185a0476b091b183f3ce28b87b03f8bd7e3a50d456c01c90fc9be68655.jpg)



(a) Mean and maximum rewards


![image](https://cdn-mineru.openxlab.org.cn/result/2026-01-02/01e9d79a-e24b-4eea-b03f-48865280d466/017860287a8db7bb0ab93900aeead46e127a5ffe89367e3eaf0fa4523c3a27d1.jpg)



(b) Average number of steps taken


![image](https://cdn-mineru.openxlab.org.cn/result/2026-01-02/01e9d79a-e24b-4eea-b03f-48865280d466/81a2ff9fc3962ffa2c6b4d4e33a2609a26d5646c7cb97b2dbefdcbd73c6267f6.jpg)



(c) Entropy



Figure 4. Evolution of key metrics during PPO training of the DSN scheduling agent. Rewards and episode length statistics were calculated across 20 evaluation episodes.


![image](https://cdn-mineru.openxlab.org.cn/result/2026-01-02/01e9d79a-e24b-4eea-b03f-48865280d466/6e62f6bc6ef376a9ffa695674bb3be8a57a2b307430f410f893e881439b73bf6.jpg)



Figure 5. Kernel density estimate of actions taken over 100 episodes for the random agent (green) and best agent (blue). Note that episodes consist of multiple steps, and results here are shown for actions selected by the agent at each step.


![image](https://cdn-mineru.openxlab.org.cn/result/2026-01-02/01e9d79a-e24b-4eea-b03f-48865280d466/b7aba0b6fd19a529c375d3506d0ebad2a8f0b490eb02362bb7bfa41a485a15ff.jpg)



Figure 6. Distribution of total rewards obtained over 100 episodes for the random agent (green) and best agent (blue). The reward distribution achieved by the trained agent exhibits an obvious shift to the right, indicating learning by the agent.


# Comparison with Trained Agent

The agent with the best performance (mean rewards in Fig. 4a) was chosen as our preliminary benchmark against the random baseline. This was the agent with the policy that had undergone roughly 700 SGD updates, or roughly 10,000 episodes. We perform 100-episode rollouts/evaluations using the best-performing agent and the random agent to sample the stochastic policies. The action distributions across all episodes shown in Fig. 5 illustrate that action masking indeed keeps agent actions to within the 286 requests for week 44 of 2016. Furthermore, Fig. 5 shows a distinct distribution of actions, indicating that, there are requests that the agent "prefers" to allocate as opposed to a uniform sampling of the action space.

From the 100 episodes, we extract schedules from the episodes with total rewards closest to the mean reward ( $\sim 161$  for

the random agent and  $\sim 184$  for the trained agent). Key performance metrics for DSN schedules include the RMS of the unsatisfied time fraction across all missions,  $U_{RMS}$ , maximum unsatisfied time fraction among all missions  $U_{max}$  and antenna utilization,  $A$ . These are defined in Eqs. 4-7.

$$
U _ {i} = \frac {T _ {R _ {i}} - T _ {S _ {i}}}{T _ {R _ {i}}} \tag {4}
$$

$$
U _ {R M S} = \sqrt {\frac {1}{N} \sum_ {i} ^ {N} U _ {i} ^ {2}} \tag {5}
$$

$$
U _ {\text {m a x}} = \max  _ {i} \left(U _ {i}\right) \tag {6}
$$

where  $T_{R_i}$  represents the total tracking time requested by the  $i$ -th mission, and  $T_{S_i}$  represents the total duration scheduled across all antennas for that mission.

$U_{max}$  is an indication of which mission has the most requests unsatisfied, while  $U_{RMS}$  provides a measure of uniformity in allocations over all missions.

$$
A = \frac {\text {t o t a l t i m e a n t e n n a s n o t i d l e}}{\text {t o t a l a v a i l b l e a n t e n n a t i m e f o r t i m e p e r i o d}} \tag {7}
$$

As seen in Table 1, the trained agent manages to satisfy 1,007 hours out of the requested 1,770 hours whereas the random agent satisfies 944 hours. Likewise, the trained agent allocates slightly more requests than the random case. The difference in  $U_{RMS}$  between the two cases is negligible. Figs. 7 and 8 show a comparison across 30 missions for the number of hours and number of tracks requested/allocated, respectively. The mission names have been omitted from these figures.


TABLE 1. Comparison of scheduled results using the mean performance of the random agent and the mean performance of the trained agent for Week 44, 2016.


<table><tr><td>Agent (Mean performance from Fig. 6)</td><td>Random</td><td>Trained</td></tr><tr><td>Hours satisfied</td><td>944</td><td>1007</td></tr><tr><td>Mean satisfied time fraction (%)</td><td>60.5</td><td>59.4</td></tr><tr><td>Number of satisfied requests</td><td>180</td><td>188</td></tr><tr><td>Mean satisfied request fraction (%)</td><td>62.9</td><td>65.7</td></tr><tr><td>RMS of unsatisfied time fraction, URMS(%)</td><td>4.3</td><td>3.9</td></tr></table>

The results presented above indicate that, while the agent is definitely learning to choose specific requests to have the environment allocate, the final output schedules exhibit only a modest improvement from randomly chosen actions. This is not surprising considering the simplicity of the agent's action space and the greedy fashion in which the environment allocates requests after receiving an index from the agent. In addition to demonstrating the feasibility of deep RL for scheduling spacecraft communications, the main accomplishment in this work is the implementation of a simple yet modular representation of the DSN scheduling problem within the deep RL framework that can be augmented with increasingly more realistic constraints and more complex RL agents. We discuss promising avenues of research in the next section.

# 5. CONCLUSIONS AND FUTURE WORK

In this paper, we presented a formulation of the DSN scheduling process as a reinforcement learning problem. An environment that encapsulates the dynamics of the scheduling problem was implemented, with the observation space being a series of quantities that represent the state of the remaining problems and the DSN antennas' availability. The agent's action space was simplified for this preliminary task — a single integer that represents the index to a list of requests for the week. Given this index, the environment then attempts to allocate the request in a greedy fashion, i.e., on the requested antenna combination with the most available time remaining.

Using the aforementioned deep RL formulation with the proximal policy optimization algorithm, an agent was trained on user loading profiles from 2016 for roughly 10M steps.

Preliminary results demonstrate observable improvement in agent performance as the underlying policy converges on an optimal policy. Due to the preliminary nature of this implementation and the complex human-in-the-loop nature of the scheduling process, comparisons could only be performed against a random agent baseline rather than the actual scheduling outcomes. These comparisons indicate that the trained agent exhibits demonstrably more reliable performance than a random agent due to the improved policy, although the absolute gains in schedule-related metrics such as unsatisfied time fraction are small.

The low performance observed in the trained agent is, perhaps unsurprisingly, due to the simplicity with which the environment and agent were designed. Indeed, it is this intentional simplicity that allows us to leverage the explainability of the agent's progress and learnings rather than performance at this juncture. This cognizance led to very careful planning of the system's implementation such that additional improvements can be made with minimal effort. Thus in ongoing research, we plan to incorporate realistic constraints elicited from requirements discussions while also scaling the datasets to represent complexity of real-world requests. We intend to improve the formulation of action spaces such that the agent also learns to split, shorten and drop tracks wherever necessary, and learn action space representations using action embeddings [28]. Currently, complexity of input datasets that the agent is being trained on has remained fairly high since we consider the oversubscribed weeks. Though the results demonstrate agent's learning capabilities, neural networks, similar to humans, benefit from gradual increase in the difficulty of the concepts it can learn [29]. To that end, we plan to integrate curriculum learning [30] and scale the training examples gradually using curriculum-based training strategies.

# ACKNOWLEDGMENTS

This effort was supported by JPL, managed by the California Institute of Technology on behalf of NASA. The authors would like to thank JPL Interplanetary Network Directorate and Deep Space Network team, and internal DSN Scheduling Strategic Initiative team members Alex Guillaume, Shahrouz Alimo, Alex Sabol and Sami Sahnoune. U.S. Government sponsorship acknowledged.

# REFERENCES



[1] NASA, “Mars 2020 perseverance rover.” [Online]. Available: mars.nasa.gov/mars2020/





[2] "Voyager." [Online]. Available: https://voyager.jpl.nasa.gov/





[3] M. D. Johnston, "Deep space network scheduling using multi-objective optimization with uncertainty," in SpaceOps 2008 Conference, 2008. [Online]. Available: http://arc.aiaa.org





[4] V. Mnih, K. Kavukcuoglu, D. Silver, A. Graves, I. Antonoglou, D. Wierstra, and M. A. Riedmiller, "Playing atari with deep reinforcement learning," CoRR, vol. abs/1312.5602, 2013.





[5] D. Silver, A. Huang, C. Maddison, A. Guez, L. Sifre, G. Driessche, J. Schrittwieser, I. Antonoglou, V. Panneershelvam, M. Lanctot, S. Dieleman, D. Grewe, J. Nham, N. Kalchbrenner, I. Sutskever, T. Lillicrap,



![image](https://cdn-mineru.openxlab.org.cn/result/2026-01-02/01e9d79a-e24b-4eea-b03f-48865280d466/d89fa5916b1c22ebd395ceee0201953c816ddaeafb400a9268394deb92eb98f2.jpg)



(a) Random Agent


![image](https://cdn-mineru.openxlab.org.cn/result/2026-01-02/01e9d79a-e24b-4eea-b03f-48865280d466/61bdd96981611a3d87dde17f0932f375fa2ebefd21d90e5eb23e9632f532b2f5.jpg)



(b) Trained Agent



Figure 7. Comparison of number of hours allocated across all missions using the random and trained agents.


![image](https://cdn-mineru.openxlab.org.cn/result/2026-01-02/01e9d79a-e24b-4eea-b03f-48865280d466/79cf8b9581252838e4f2195f34576717b905e24093c2d7c1e3de3fd0083163c7.jpg)



(a) Random Agent


![image](https://cdn-mineru.openxlab.org.cn/result/2026-01-02/01e9d79a-e24b-4eea-b03f-48865280d466/6183f3b8eaf947dbd12b9e5c66a0223df93074537823e8ae66fa0998983cb605.jpg)



(b) Trained Agent



Figure 8. Comparison of number of requests scheduled across all missions using the random and trained agents.


M. Leach, K. Kavukcuoglu, T. Graepel, and D. Hassabis, “Mastering the game of go with deep neural networks and tree search,” Nature, vol. 529, pp. 484–489, 01 2016.



[6] R. S. Sutton and A. G. Barto, Reinforcement learning: An introduction. MIT press, 2018.





[7] Y. Wang, H. Liu, W. Zheng, Y. Xia, Y. Li, P. Chen, K. Guo, and H. Xie, "Multi-objective workflow scheduling with deep-Q-network-based multi-agent reinforcement learning," IEEE Access, vol. 7, pp. 39974-39982, 2019.





[8] J. Wang, C. Xu, Y. Huangfu, R. Li, Y. Ge, and J. Wang, "Deep Reinforcement Learning for Scheduling in Cellular Networks," may 2019. [Online]. Available: https://arxiv.org/abs/1905.05914





[9] B. Balaji, J. Bell-Masterson, E. Bilgin, A. Damianou, P. M. Garcia, A. Jain, R. Luo, A. Maggiar, B. Narayanaswamy, and C. Ye,



"ORL: Reinforcement Learning Benchmarks for Online Stochastic Optimization Problems," arXiv, pp. arXiv-1911, 2019. [Online]. Available: www.aaai.org http://arxiv.org/abs/1911.10641



[10] W. Zhang and T. G. Dietterich, “A Reinforcement Learning Approach to Job-Shop Scheduling,” in Proceedings of the 14th International Joint Conference on Artificial Intelligence - Volume 2, ser. IJCAI'95. San Francisco, CA, USA: Morgan Kaufmann Publishers Inc., 1995, pp. 1114–1120.





[11] A. Rubinsztejn, R. Sood, and F. E. Laipert, "Neural network optimal control in astrodynamics: Application to the missed thrust problem," Acta Astronautica, vol. 176, pp. 192-203, nov 2020.





[12] P. V. R. Ferreira, R. Paffenroth, A. M. Wyglinski, T. M. Hackett, S. G. Bilen, R. C. Reinhart, and D. J. Mortensen, "Multi-objective reinforcement learning-based deep neural networks for cognitive space communications," in 2017 Cognitive Communications for Aerospace





Applications Workshop, CCAA 2017. Institute of Electrical and Electronics Engineers Inc., aug 2017.





[13] B. J. Clement and M. D. Johnston, “The deep space network scheduling problem,” in Proceedings of the National Conference on Artificial Intelligence, vol. 3. Pasadena, CA: Jet Propulsion Laboratory, National Aeronautics and Space ..., 2005, pp. 1514–1520.





[14] M. D. Johnston, D. Tran, B. Arroyo, S. Sorensen, P. Tay, B. Carruth, A. Coffman, and M. Wallace, "Automated scheduling for NASA's Deep Space Network," AI Magazine, vol. 35, no. 4, pp. 7-25, dec 2014.





[15] M. D. Johnston, "User preference optimization for oversubscribed scheduling of nasa's deep space network," in 11th International Workshop on Planning and Scheduling for Space (IWPSS), Berkeley, California, USA, July 2019, pp. 86-92.





[16] A. Guillaume, S. Lee, Y. F. Wang, H. Zheng, R. Hovden, S. Chau, Y. W. Tung, and R. J. Terrile, "Deep space network scheduling using evolutionary computational methods," in IEEE Aerospace Conference Proceedings, 2007.





[17] G. Rueda Oller, "Space Mission Scheduling Toolkit for Long-Term Deep Space Network Loading Analyses and Strategic Planning," 2019.





[18] J. A. Sabol, R. Alimo, M. Hoffmann, E. Goh, B. Wilson, and M. Johnston, Towards Automated Scheduling of NASA's Deep Space Network: A Mixed Integer Linear Programming Approach. [Online]. Available: https://arc.aiaa.org/doi/abs/10.2514/6.2021-0667





[19] T. Hackett, S. Bilen, and M. D. Johnston, "Investigating a demand access scheduling paradigm for NASA's deep space network," in Proc. 11th Int. Workshop Plan. Scheduling, 2019, pp. 51-60.





[20] T. M. Hackett, "Applying artificial intelligence to space communications networks: Cognitive real-time link layer adaptations through rapid orbit planning," Ph.D. dissertation, The Pennsylvania State University, 2019.





[21] G. Brockman, V. Cheung, L. Pettersson, J. Schneider, J. Schulman, J. Tang, and W. Zaremba, “Openai gym,” 2016.





[22] OpenAI, "Openai five," https://blog.openai.com/openai-five/, 2018.





[23] J. Schulman, F. Wolski, P. Dhariwal, A. Radford, and O. Klimov, "Proximal Policy Optimization Algorithms," jul 2017. [Online]. Available: http://arxiv.org/abs/1707.06347





[24] E. Liang, R. Liaw, P. Moritz, R. Nishihara, R. Fox, K. Goldberg, J. E. Gonzalez, and M. I. Jordan, "RLlib: Abstractions for Distributed Reinforcement Learning," Tech. Rep., jul 2018. [Online]. Available: http://rlib.io





[25] H. Mao, M. Alizadeh, I. Menache, and S. Kandula, “Resource management with deep reinforcement learning,” in HotNets 2016 - Proceedings of the 15th ACM Workshop on Hot Topics in Networks. New York, New York, USA: Association for Computing Machinery, Inc, nov 2016, pp. 50-56. [Online]. Available: http://dl.acm.org/citation.cfm?doid=3005745.3005750





[26] S. Kullback and R. A. Leibler, “On information and sufficiency,” Ann. Math. Statist., vol. 22, no. 1, pp. 79–86, 03 1951. [Online]. Available: https://doi.org/10.1214/aoms/1177729694





[27] J. Schulman, P. Moritz, S. Levine, M. Jordan, and P. Abbeel, “High-dimensional continuous control using generalized advantage estimation,” 2018.





[28] H. Mao, M. Schwarzkopf, S. B. Venkatakrishnan, Z. Meng, and M. Alizadeh, "Learning Scheduling Algorithms for Data Processing Clusters," SIGCOMM 2019 - Proceedings of the 2019 Conference of the ACM Special Interest Group on Data Communication, pp. 270-288, oct 2018. [Online]. Available: http://arxiv.org/abs/1810.01963





[29] J. Elman, “Learning and development in neural networks: the importance of starting small,” Cognition, vol. 48, pp. 71–99, 1993.





[30] Y. Bengio, J. Louradour, R. Collobert, and J. Weston, "Curriculum learning," in Proceedings of the 26th annual international conference on machine learning, 2009, pp. 41-48.

