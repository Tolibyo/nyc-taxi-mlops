

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin

class RareZoneBucketer (BaseEstimator, TransformerMixin):
    def __init__(self, top_n=250):
        self.top_n = top_n
    
    def fit(self, X, y=None):
        top = X['PULocationID'].value_counts().index[:self.top_n]
        self.top_zones_ = top
        return self

    def transform(self, X):
        X = X.copy()
        mask = X['PULocationID'].isin(self.top_zones_)
        X['PULocationID'] = np.where(mask, X['PULocationID'], -1)
        return X
    

class CategoryCaster(BaseEstimator, TransformerMixin):
    def __init__(self, columns):
        self.columns = columns

    def fit(self, X, y=None):
        return self
    
    def transform(self, X):
        X = X.copy()
        for col in self.columns:
            X[col] = X[col].astype("category")
        return X