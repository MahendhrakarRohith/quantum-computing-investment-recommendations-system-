import numpy as np
from qiskit_optimization.applications import Knapsack
from qiskit_optimization.algorithms import MinimumEigenOptimizer
from qiskit_algorithms import QAOA
from qiskit_algorithms.optimizers import COBYLA
from qiskit.primitives import Sampler

def optimize_portfolio_qaoa(budget: float, ai_predictions: list):
    """
    Uses Quantum Computing (QAOA) to find the mathematically optimal combination
    of whole shares to maximize expected return within a strict budget constraint.
    """
    print(f"⚛️ Initializing Quantum Optimization for Budget: ₹{budget}")

    # 1. Flatten the data for the Quantum Knapsack
    # We break down stocks into individual "shares" so the algorithm can decide
    # exactly how many of each to buy (e.g., 0, 1, or 2 shares of TATASTEEL)
    values = []  # The expected profit (₹)
    weights = [] # The cost of the share (₹)
    labels = []  # To remember which share is which

    for stock in ai_predictions:
        symbol = stock['symbol']
        price = stock['price']
        expected_return_pct = stock['expected_return_pct'] / 100.0
        
        # Calculate expected profit in Rupees for one share
        expected_profit = price * expected_return_pct
        
        # Calculate the maximum number of shares the user could mathematically afford
        max_possible_shares = int(budget // price)
        
        # Add each possible share to our quantum problem pool
        for i in range(max_possible_shares):
            values.append(expected_profit)
            weights.append(price)
            labels.append(symbol)

    # Edge Case: If the budget is too small to buy anything
    if not weights:
        return {"error": "Budget too low to purchase any available assets."}

    # 2. Formulate the QUBO (Quadratic Unconstrained Binary Optimization) Problem
    # This translates our finance problem into quantum physics equations
    print(f"📦 Formulating Knapsack with {len(weights)} possible share combinations...")
    knapsack = Knapsack(values=values, weights=weights, max_weight=budget)
    quadratic_program = knapsack.to_quadratic_program()

    # 3. Setup the QAOA Quantum Algorithm
    # We use COBYLA as the classical optimizer to tune the quantum gates
    optimizer = COBYLA(maxiter=50)
    sampler = Sampler() # Simulates the quantum measurements
    
    qaoa = QAOA(sampler=sampler, optimizer=optimizer, reps=1)
    eigen_optimizer = MinimumEigenOptimizer(qaoa)

    # 4. EXECUTING THE QUANTUM CIRCUIT
    print("⚡ Running QAOA Circuit (This may take a moment on a classical CPU)...")
    result = eigen_optimizer.solve(quadratic_program)

    # 5. Decode the Quantum Result back into a Financial Portfolio
    optimal_allocation = {}
    total_spent = 0.0
    total_expected_profit = 0.0

    # result.x is an array of 1s and 0s (1 = buy this share, 0 = do not buy)
    for i, is_selected in enumerate(result.x):
        if is_selected == 1:
            symbol = labels[i]
            if symbol not in optimal_allocation:
                optimal_allocation[symbol] = {
                    "shares": 0, 
                    "price": weights[i], 
                    "total_value": 0.0,
                    "expected_profit": 0.0
                }
            
            optimal_allocation[symbol]["shares"] += 1
            optimal_allocation[symbol]["total_value"] += weights[i]
            optimal_allocation[symbol]["expected_profit"] += values[i]
            
            total_spent += weights[i]
            total_expected_profit += values[i]

    uninvested_cash = budget - total_spent

    return {
        "status": "success",
        "strategy": "Quantum QAOA Optimization",
        "budget": budget,
        "total_spent": round(total_spent, 2),
        "uninvested_cash": round(uninvested_cash, 2),
        "projected_return_inr": round(total_expected_profit, 2),
        "projected_return_pct": round((total_expected_profit / total_spent) * 100, 2) if total_spent > 0 else 0,
        "portfolio": optimal_allocation
    }


# --- QUICK TEST SCRIPT ---
if __name__ == "__main__":
    # Mock data from your Machine Learning models
    mock_ai_predictions = [
        {"symbol": "TATASTEEL", "price": 150.0, "expected_return_pct": 12.0},  # Cheap, high return
        {"symbol": "ZOMATO",    "price": 200.0, "expected_return_pct": 15.0},  # Medium, very high return
        {"symbol": "SBIN",      "price": 750.0, "expected_return_pct": 5.0},   # Expensive, lower return
        {"symbol": "RELIANCE",  "price": 2900.0,"expected_return_pct": 8.0}    # Too expensive for 1000
    ]
    
    user_budget = 1000.0
    
    final_portfolio = optimize_portfolio_qaoa(user_budget, mock_ai_predictions)
    
    import json
    print("\n🔮 QUANTUM OPTIMIZATION COMPLETE:")
    print(json.dumps(final_portfolio, indent=2))