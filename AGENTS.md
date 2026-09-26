# AGENTS.md

This document defines the code style and development standards that every AI agent must strictly follow when generating or modifying Python code in this repository.

## 1. Core Principles

K.I.S.S. Method (Keep It Simple, Stupid):

Prefer simple, direct, and idiomatic solutions.

Avoid premature abstractions, unnecessary design patterns, redundant wrappers, or boilerplate code.

Do not produce overly verbose changes or refactorings unless strictly necessary; if a shorter, cleaner solution achieves the same result, use it.

Targeted Modifications:

Only modify the specific code sections required for the task.

Do not rewrite or reorganise untouched areas of a file if not necessary.

## 2. Method Docstrings (Pandas / NumPy Style)

Every method, function, or class must be documented strictly using the NumPy / Pandas docstring standard.

Required Structure:

A concise, one-line summary.

(Optional) An extended summary if the logic requires additional context.

A Parameters section detailing parameter names, types, and descriptions.

A Returns (or Yields) section detailing return types and descriptions.

A Raises section if the function explicitly raises errors.

An Examples section containing at least one practical doctest example (>>>).

Example Format:

```python
def process_data(
    data: pd.DataFrame, 
    threshold: float = 0.5, 
    drop_na: bool = True
) -> pd.DataFrame:
    """
    Filter and scale numeric columns based on a minimum variance threshold.

    Parameters
    ----------
    data : pd.DataFrame
        Input DataFrame containing numeric features to be processed.
    threshold : float, default 0.5
        Minimum variance threshold. Columns below this value are dropped.
    drop_na : bool, default True
        Whether to drop rows containing NaN values prior to processing.

    Returns
    -------
    pd.DataFrame
        The processed DataFrame with filtered numeric columns.

    Raises
    ------
    ValueError
        If the input DataFrame is empty or contains no numeric columns.

    Examples
    --------
    >>> import pandas as pd
    >>> df = pd.DataFrame({'a': [1, 2, 3], 'b': [0, 0, 0]})
    >>> process_data(df, threshold=0.1)
       a
    0  1
    1  2
    2  3
    """
```

## 3. Inline Comments

Reserve for Critical or Complex Passages: Do not write inline comments to explain obvious or self-explanatory code.

Focus on "Why", Not "What": Explain the underlying reasoning, non-obvious algorithms, or edge-case handling.

Conciseness: Keep comments short, clear, and placed directly above the code in question or alongside it.

Example:
```
# ❌ INCORRECT (Obvious / redundant comment)
i = i + 1  # Increment i by 1

# ✅ CORRECT (Explains a non-trivial optimization / choice)
# Use bitwise AND to check parity: faster than modulo (%) in hot loops
is_even = (val & 1) == 0
```

## 4. Full Code Example
```python
import pandas as pd
import numpy as np

def calculate_weighted_moving_average(
    df: pd.DataFrame, 
    column: str, 
    weights: list[float]
) -> pd.Series:
    """
    Calculate the weighted moving average of a specific DataFrame column.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing the target column.
    column : str
        Name of the column on which to calculate the average.
    weights : list of float
        List of weights for the moving window. The sum of weights must equal 1.0.

    Returns
    -------
    pd.Series
        Series representing the weighted moving average values.

    Raises
    ------
    KeyError
        If `column` does not exist in `df`.
    ValueError
        If the sum of `weights` does not approximate 1.0.

    Examples
    --------
    >>> import pandas as pd
    >>> df = pd.DataFrame({'price': [10.0, 11.0, 12.0, 15.0]})
    >>> calculate_weighted_moving_average(df, 'price', [0.2, 0.3, 0.5])
    0      NaN
    1      NaN
    2    11.3
    3    13.3
    dtype: float64
    """
    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found in DataFrame.")

    # Small tolerance check to handle floating-point arithmetic precision errors
    if not np.isclose(sum(weights), 1.0):
        raise ValueError("Weights must sum to 1.0.")

    window_size = len(weights)
    
    # Reverse weights in array dot product to align with chronological window order
    return df[column].rolling(window=window_size).apply(
        lambda x: np.dot(x, weights[::-1]), raw=True
    )
```
