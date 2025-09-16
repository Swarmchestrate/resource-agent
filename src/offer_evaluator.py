import numpy as np
import random


def argsort_with_ties(values):
    sorted_indices = np.argsort(values, kind='stable')  # Stable sort
    ranks = np.zeros(len(values), dtype=int)
    sorted_values = np.array(values)[sorted_indices]

    rank = 0
    while rank < len(sorted_values):
        same_value_indices = [i for i in range(rank, len(sorted_values)) if sorted_values[i] == sorted_values[rank]]
        max_rank = max(same_value_indices)
        for i in same_value_indices:
            ranks[sorted_indices[i]] = max_rank
        rank += len(same_value_indices)
    return ranks + 1


class OfferEvaluator:
    def __init__(self, offer_data):
        self.offer_data = offer_data
        self.qos_priority = offer_data["qos_priority"]
        self.reliability = np.asarray(offer_data["reliability"])
        self.num_offer = self.reliability.shape[0]

    def rank_offers_without_reliability(self):
        total_cost = np.zeros(self.num_offer)

        for i, qos in enumerate(self.qos_priority):
            raw_data = np.asarray(self.offer_data[qos])
            max_val = raw_data.max()
            min_val = raw_data.min()

            # Check if max and min values are the same to avoid division by zero
            if max_val == min_val:
                normalized_data = np.zeros_like(raw_data)  # or any constant value, e.g., np.ones_like(raw_data)
            else:
                normalized_data = (raw_data - min_val) / (max_val - min_val)

            if qos == "bandwidth":
                normalized_data = -normalized_data  # higher numeric value -> lower cost
            total_cost = total_cost + self.qos_priority[qos] * normalized_data

        # offer_index = np.argmin(total_cost)
        # return offer_index
        return np.argsort(total_cost)

    def rank_offers_with_reliability_addition(self):
        total_cost = np.zeros(self.num_offer)

        for i, qos in enumerate(self.qos_priority):
            raw_data = np.asarray(self.offer_data[qos])
            max_val = raw_data.max()
            min_val = raw_data.min()

            # Check if max and min values are the same
            if max_val == min_val:
                normalized_data = np.zeros_like(raw_data)
            else:
                normalized_data = (raw_data - min_val) / (max_val - min_val)

            if qos == "bandwidth":
                normalized_data = -normalized_data  # higher numeric value -> lower cost
            total_cost = total_cost + self.qos_priority[qos] * normalized_data

        total_cost = total_cost - self.reliability  # more reliable -> less cost
        # offer_index = np.argmin(total_cost)
        # return offer_index
        return np.argsort(total_cost)

    def rank_offers_with_reliability_multiplication(self):
        total_cost = np.zeros(self.num_offer)

        for i, qos in enumerate(self.qos_priority):
            raw_data = np.asarray(self.offer_data[qos])
            max_val = raw_data.max()
            min_val = raw_data.min()

            # Check if max and min values are the same
            if max_val == min_val:
                normalized_data = np.zeros_like(raw_data)
            else:
                normalized_data = (raw_data - min_val) / (max_val - min_val)

            if qos == "bandwidth":
                normalized_data = -normalized_data  # higher numeric value -> lower cost
            total_cost = total_cost + self.qos_priority[qos] * normalized_data

        total_cost = np.multiply((1.0 - self.reliability), total_cost)  # more reliable -> less cost
        # offer_index = np.argmin(total_cost)
        # return offer_index
        return np.argsort(total_cost)

    def vote_offers_without_reliability(self):
        """
        vote_w_reliability: votes offers without reliability
        Can handle the problem when same QoS values are submitted multiple times

        :return: ranked list of offers
        """
        borda_scores = np.zeros((len(self.qos_priority), self.num_offer))

        for i, qos in enumerate(self.qos_priority):
            raw_data = np.asarray(self.offer_data[qos])

            # Determine sorting direction based on QoS type
            if qos == "bandwidth":
                # For bandwidth, higher is better (descending)
                scores = argsort_with_ties(raw_data)
            else:
                scores = argsort_with_ties(-raw_data)

            borda_scores[i, :] = scores * self.qos_priority[qos]
        sum_array = np.sum(borda_scores, axis=0)
        return np.argsort(sum_array)[::-1]

    # def vote_offers_without_reliability(self):
    #     """
    #     Original vote_wo_offers
    #
    #     """
    #
    #     borda_scores = np.zeros((len(self.qos_priority), self.num_offer))
    #
    #     for i, qos in enumerate(self.qos_priority):
    #         raw_data = np.asarray(self.offer_data[qos])
    #
    #         if qos == "bandwidth":
    #             sorted_indices = np.argsort(-raw_data, axis=0)
    #         else:
    #             sorted_indices = np.argsort(raw_data, axis=0)
    #
    #         scores = np.zeros(self.num_offer)
    #         for rank, index in enumerate(sorted_indices):
    #             scores[index] = self.num_offer - rank
    #
    #         borda_scores[i, :] = scores
    #
    #     sum_array = np.sum(borda_scores, axis=0)
    #     # offer_index = np.argmax(sum_array)
    #     # return offer_index
    #     return np.argsort(sum_array)[::-1]

    def vote_offers_with_reliability_addition(self):

        """
        vote_w_reliability: votes offers with reliability as a term to be summed
        Can handle the problem when same QoS values are submitted multiple times

        :return: ranked list of offers
        """

        borda_scores = np.zeros((len(self.qos_priority) + 1, self.num_offer))
        borda_scores[len(self.qos_priority), :] = argsort_with_ties(self.reliability)

        for i, qos in enumerate(self.qos_priority):
            raw_data = np.asarray(self.offer_data[qos])

            # Determine sorting direction based on QoS
            if qos == "bandwidth":
                # sorted_indices = np.argsort(-raw_data)
                scores = argsort_with_ties(raw_data)
            else:
                # sorted_indices = np.argsort(raw_data)
                scores = argsort_with_ties(-raw_data)

            borda_scores[i, :] = scores * self.qos_priority[qos]
        sum_array = np.sum(borda_scores, axis=0)
        return np.argsort(sum_array)[::-1]

    # def vote_offers_with_reliability_addition(self):
    #     """
    #     Original vote_wo_offers
    #
    #     """
    #     borda_scores = np.zeros((len(self.qos_priority) + 1, self.num_offer))
    #
    #     sorted_reliability = np.argsort(-self.reliability, axis=0)
    #     scores = np.zeros(self.num_offer)
    #     for rank, index in enumerate(sorted_reliability):
    #         scores[index] = self.num_offer - rank
    #
    #     borda_scores[len(self.qos_priority), :] = scores
    #
    #     for i, qos in enumerate(self.qos_priority):
    #         raw_data = np.asarray(self.offer_data[qos])
    #
    #         if qos == "bandwidth":
    #             sorted_indices = np.argsort(-raw_data, axis=0)
    #         else:
    #             sorted_indices = np.argsort(raw_data, axis=0)
    #
    #         scores = np.zeros(self.num_offer)
    #         for rank, index in enumerate(sorted_indices):
    #             scores[index] = self.num_offer - rank
    #
    #         borda_scores[i, :] = scores
    #
    #     sum_array = np.sum(borda_scores, axis=0)
    #     # offer_index = np.argmax(sum_array)
    #     # return offer_index
    #     return np.argsort(sum_array)[::-1]

    def vote_offers_with_reliability_multiplication(self):

        """
        vote_w_reliability_mul: votes offers with reliability as a multiplication term
        Can handle the problem when same QoS values are submitted multiple times

        :return: ranked list of offers
        """
        borda_scores = np.zeros((len(self.qos_priority), self.num_offer))

        for i, qos in enumerate(self.qos_priority):
            raw_data = np.asarray(self.offer_data[qos])

            # Determine sorting direction
            if qos == "bandwidth":
                # sorted_indices = np.argsort(-raw_data)
                scores = argsort_with_ties(raw_data)
            else:
                # sorted_indices = np.argsort(raw_data)
                scores = argsort_with_ties(-raw_data)

            # Multiply scores by reliability
            borda_scores[i, :] = np.multiply(self.reliability, scores) * self.qos_priority[qos]
        sum_array = np.sum(borda_scores, axis=0)
        return np.argsort(sum_array)[::-1]

    # def vote_offers_with_reliability_multiplication(self):
    #     borda_scores = np.zeros((len(self.qos_priority), self.num_offer))
    #
    #     for i, qos in enumerate(self.qos_priority):
    #         raw_data = np.asarray(self.offer_data[qos])
    #
    #         if qos == "bandwidth":
    #             sorted_indices = np.argsort(-raw_data, axis=0)
    #         else:
    #             sorted_indices = np.argsort(raw_data, axis=0)
    #
    #         scores = np.zeros(self.num_offer)
    #         for rank, index in enumerate(sorted_indices):
    #             scores[index] = self.num_offer - rank
    #
    #         borda_scores[i, :] = np.multiply((self.reliability), scores)
    #
    #     sum_array = np.sum(borda_scores, axis=0)
    #     # offer_index = np.argmax(sum_array)
    #     # return offer_index
    #     return np.argsort(sum_array)[::-1]


def genetic_algorithm(offer_data, include_reliability=False,
                      pop_size=100, generations=50, mutation_rate=0.1):
    qos_priority = offer_data["qos_priority"]
    reliability = np.asarray(offer_data["reliability"])
    num_offers = reliability.shape[0]
    # Initialize population
    population = np.random.randint(0, num_offers, size=pop_size)

    def fitness_function(solution, offer_data, qos_priority, reliability=None, include_reliability=False):
        total_cost = 0.0

        # Iterate through objectives
        for qos, weight in qos_priority.items():
            raw_data = np.asarray(offer_data[qos])
            max_val = raw_data.max()
            min_val = raw_data.min()

            # Normalize
            if max_val != min_val:
                normalized = (raw_data - min_val) / (max_val - min_val)
            else:
                normalized = np.zeros_like(raw_data)

            if qos == "bandwidth":
                normalized = -normalized  # Higher is worse

            total_cost += weight * normalized[solution]

        # Include reliability if specified
        if include_reliability:
            if reliability is not None:
                total_cost -= reliability[solution]  # Subtract for higher reliability
        return total_cost

    def evaluate_population(population):
        return np.array([
            fitness_function(ind, offer_data, qos_priority, reliability, include_reliability)
            for ind in population
        ])

    for generation in range(generations):
        # Evaluate fitness
        fitness_scores = evaluate_population(population)

        # Select parents (roulette wheel selection based on inverse fitness)
        probabilities = 1 / (1 + fitness_scores)
        probabilities /= probabilities.sum()
        parents = np.random.choice(population, size=pop_size, p=probabilities)

        # Crossover
        offspring = []
        for _ in range(pop_size // 2):
            p1, p2 = random.sample(list(parents), 2)
            if random.random() < 0.5:  # Swap or keep parents
                offspring.append(p1)
                offspring.append(p2)
            else:
                offspring.append(p2)
                offspring.append(p1)

        population = np.array(offspring[:pop_size])

        # Mutation
        for i in range(pop_size):
            if random.random() < mutation_rate:
                population[i] = random.randint(0, num_offers - 1)

    # Final ranking
    final_fitness = evaluate_population(population)
    ranked_indices = np.argsort(final_fitness)
    return ranked_indices

