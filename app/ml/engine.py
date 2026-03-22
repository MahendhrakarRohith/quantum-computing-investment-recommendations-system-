import pandas as pd
import numpy as np

# statsmodels is optional; fall back to a naive forecast if it's missing
try:
    from statsmodels.tsa.arima.model import ARIMA
    _arima_available = True
except ImportError:
    ARIMA = None
    _arima_available = False
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout
from tensorflow.keras.layers import Input
from tensorflow.keras.callbacks import EarlyStopping

class PredictionEngine:
    def __init__(self, csv_path):
        self.df = pd.read_csv(csv_path)
        self.scaler = MinMaxScaler(feature_range=(0, 1))

    def get_arima_prediction(self):
        """Predicts the next day's price using ARIMA"""
        history = self.df['close'].tolist()
        # If statsmodels is unavailable, return a simple persistence forecast to avoid crashes.
        if not _arima_available or len(history) < 10:
            return float(history[-1])

        # Order (5,1,0) is a standard starting point for stock data
        model = ARIMA(history, order=(5,1,0))
        model_fit = model.fit()
        output = model_fit.forecast()
        return float(output[0])
# ... (keep your existing __init__ and arima functions above this) ...

    def get_lstm_prediction(self, epochs=50): 
        # Note: We increased epochs to 50, but Early Stopping will cut it off much sooner!
        
        data = self.df.filter(['close']).values
        scaler = MinMaxScaler(feature_range=(0, 1))
        scaled_data = scaler.fit_transform(data)

        # Look back 60 days to predict tomorrow
        time_step = 60
        if len(scaled_data) <= time_step:
            return float(self.df['close'].iloc[-1]) # Fallback if not enough data

        x_train, y_train = [], []
        for i in range(time_step, len(scaled_data)):
            x_train.append(scaled_data[i-time_step:i, 0])
            y_train.append(scaled_data[i, 0])

        x_train, y_train = np.array(x_train), np.array(y_train)
        x_train = np.reshape(x_train, (x_train.shape[0], x_train.shape[1], 1))

        # 🧠 THE UPGRADED ANTI-OVERFITTING NEURAL NETWORK
        model = Sequential()
        
        # Layer 1: LSTM with 20% Dropout (Neural Amnesia)
        model.add(LSTM(units=50, return_sequences=True, input_shape=(x_train.shape[1], 1)))
        model.add(Dropout(0.2)) 
        
        # Layer 2: LSTM with 20% Dropout 
        model.add(LSTM(units=50, return_sequences=False))
        model.add(Dropout(0.2)) 
        
        # Output Layers
        model.add(Dense(units=25))
        model.add(Dense(units=1))

        model.compile(optimizer='adam', loss='mean_squared_error')

        # 🛑 EARLY STOPPING LOGIC
        # Monitor the Validation Loss. If the AI doesn't improve for 5 cycles, stop training immediately.
        # restore_best_weights=True ensures we keep the smartest version of the model before it overfit.
        early_stop = EarlyStopping(monitor='val_loss', patience=5, restore_best_weights=True)

        # Train the model
        # validation_split=0.1 means we hide 10% of the data during training to test for overfitting live
        model.fit(
            x_train, y_train, 
            batch_size=32, 
            epochs=epochs, 
            validation_split=0.1, 
            callbacks=[early_stop], 
            verbose=0 # Set to 1 if you want to watch the epochs train in the terminal
        )

        # Predict Tomorrow
        last_60_days = scaled_data[-time_step:]
        X_test = np.array([last_60_days])
        X_test = np.reshape(X_test, (X_test.shape[0], X_test.shape[1], 1))

        pred_price = model.predict(X_test, verbose=0)
        pred_price = scaler.inverse_transform(pred_price)

        return float(pred_price[0][0])
