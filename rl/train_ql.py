"""
Phase 4 - Learned Signal Policy.

Trains a tabular Q-learning agent (sumo-rl's QLAgent + epsilon-greedy
exploration) on the Astra Biz Center junction: it observes (current green
phase, binned queue length) every 5 simulated seconds and learns which phase
to hold or switch to in order to minimize accumulated waiting time.
"""
import pickle

from sumo_rl import SumoEnvironment
from sumo_rl.agents.ql_agent import QLAgent
from sumo_rl.exploration.epsilon_greedy import EpsilonGreedy

from discretized_obs import DiscretizedObservationFunction

NET = "sumo/astra_biz_center/astra_biz_center.net.xml"
ROUTE = "sumo/astra_biz_center/astra_biz_center.rou.xml"
Q_TABLE_OUT = "rl/q_table.pkl"

NUM_EPISODES = 40
SIM_SECONDS = 3600
DELTA_TIME = 5
ALPHA = 0.1
GAMMA = 0.95
EPSILON_INITIAL = 1.0
EPSILON_MIN = 0.05
EPSILON_DECAY = 0.95  # applied once per episode


if __name__ == "__main__":
    env = SumoEnvironment(
        net_file=NET,
        route_file=ROUTE,
        use_gui=False,
        num_seconds=SIM_SECONDS,
        delta_time=DELTA_TIME,
        yellow_time=3,
        min_green=8,
        max_green=45,
        single_agent=True,
        reward_fn="diff-waiting-time",
        observation_class=DiscretizedObservationFunction,
        sumo_seed=42,
        sumo_warnings=False,
        add_per_agent_info=False,
    )

    ts_id = env.ts_ids[0]
    initial_state, _ = env.reset()
    initial_state = tuple(initial_state)

    exploration = EpsilonGreedy(initial_epsilon=EPSILON_INITIAL, min_epsilon=EPSILON_MIN, decay=1.0)
    agent = QLAgent(
        starting_state=initial_state,
        state_space=env.observation_space,
        action_space=env.action_space,
        alpha=ALPHA,
        gamma=GAMMA,
        exploration_strategy=exploration,
    )

    epsilon = EPSILON_INITIAL
    episode_rewards = []

    for episode in range(1, NUM_EPISODES + 1):
        exploration.epsilon = epsilon
        state, _ = env.reset()
        agent.state = tuple(state)
        if agent.state not in agent.q_table:
            agent.q_table[agent.state] = [0 for _ in range(env.action_space.n)]

        done = False
        total_reward = 0.0
        while not done:
            action = agent.act()
            next_state, reward, terminated, truncated, info = env.step(action)
            done = terminated or truncated
            agent.learn(next_state=tuple(next_state), reward=reward, done=done)
            total_reward += reward

        episode_rewards.append(total_reward)
        epsilon = max(EPSILON_MIN, epsilon * EPSILON_DECAY)
        print(
            f"Episode {episode:2d}/{NUM_EPISODES} | "
            f"total_reward={total_reward:9.1f} | epsilon={epsilon:.3f} | "
            f"states_seen={len(agent.q_table)}"
        )

    env.close()

    with open(Q_TABLE_OUT, "wb") as f:
        pickle.dump(dict(agent.q_table), f)
    print(f"\nSaved Q-table ({len(agent.q_table)} states) to {Q_TABLE_OUT}")
