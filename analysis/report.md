# TrafficTwin Results — Astra Biz Center Junction

## Metrics

| Metric | Fixed-timer baseline | Learned (Q-learning) | Improvement |
|---|---|---|---|
| Mean queue length (vehicles) | 629.9 | 522.9 | 17.0% |
| Mean waiting time (s/vehicle) | 584.8 | 363.2 | 37.9% |
| Mean speed (m/s) | 1.25 | 1.62 | 29.3% |
| Peak queue length (vehicles) | 1070 | 997 | - |

## Explanation (generated locally by qwen2.5:7b-instruct via Ollama)

In this experiment, two traffic signal control strategies were tested on a digital twin of a real 4-way junction in Astra Biz Center, BSD City, Tangerang, Indonesia. The junction was modeled using the Simulation of Urban Mobility (SUMO) software to accurately represent its real-world geometry and an Indonesian motorcycle-heavy traffic mix. Each strategy operated for one simulated hour. Strategy A, known as the fixed-timer baseline, used the existing traffic light program that switches based on a predetermined schedule irrespective of current traffic conditions. In contrast, Strategy B employed a Q-learning reinforcement-learning agent that observed queue lengths every 5 seconds and dynamically decided whether to keep or switch the green light.

The results were unequivocal—Strategy B, the learned policy, outperformed Strategy A across all metrics. Specifically, during the one-hour simulation period, the mean queue length was significantly lower at 522.9 vehicles for the learned policy compared to 629.9 vehicles for the fixed-timer baseline, a difference of 17.0%. Additionally, the average waiting time per vehicle was markedly shorter—363.2 seconds with the learned policy versus 584.8 seconds for the fixed-timer baseline, representing a 37.9% reduction. Furthermore, the mean speed in the junction was higher at 1.6 meters per second under the learned policy compared to 1.3 meters per second under the fixed-timer baseline, an improvement of 29.3%.

While these findings are clear and demonstrate significant benefits for the learned policy strategy, it is important to consider several caveats before implementing this approach in real-world conditions. The synthetic traffic demand used in this simulation heavily favored motorcycles and was estimated at approximately 4300 vehicles per hour, likely exceeding the real capacity of a single junction network, leading to gridlock conditions. This oversaturated scenario does not reflect typical busy but non-gridlocked traffic conditions one might encounter in actual urban areas. Moreover, the small state space and relatively short training period for the learned policy could limit its generalizability and robustness under more diverse or extended real-world scenarios. Despite these limitations, the demonstrated improvements suggest that a well-trained reinforcement learning agent could offer substantial benefits when applied to similar oversaturated junctions in the future, although further testing and adjustments would be necessary before deployment in live traffic conditions.
