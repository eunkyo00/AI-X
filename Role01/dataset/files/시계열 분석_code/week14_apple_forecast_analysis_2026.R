library(forecast)
library(dlm)
library(ggplot2)
library(dplyr)
library(tidyr)

setwd("C:/Users/User/Desktop/시계열분석/시계열분석 데이터")
apple <- read.csv("apple.csv", stringsAsFactors = FALSE)

# sales 열의 쉼표 제거 후 숫자 변환
apple$sales <- as.numeric(gsub(",", "", apple$sales))

# 시계열 객체 생성 (분기 -> frequency = 4)
sales_ts <- ts(apple$sales, 
               start = c(2015, 1), 
               frequency = 4)

# =============================================================================
# 방법 1: SARIMA 모형 (auto.arima)
# =============================================================================
cat("/n/n========== 방법 1: SARIMA 모형 ==========/n/n")

arima_model <- auto.arima(sales_ts, 
                          seasonal = TRUE,
                          stepwise = FALSE,
                          approximation = FALSE,
                          trace = FALSE)

cat("선택된 ARIMA 모형:/n")
print(arima_model)

# 잔차 진단
cat("/n잔차 진단 (Ljung-Box p > 0.05면 양호):/n")
checkresiduals(arima_model)

# 2024년 예측
forecast_arima <- forecast(arima_model, h = 4)
cat("/n2024년 예측 (SARIMA):/n")
print(forecast_arima)

# 시각화
plot(forecast_arima,
     main = "SARIMA 예측 - Apple 매출 (2024 Q1-Q4)",
     ylab = "매출액 (백만 달러)", xlab = "연도")
grid()


# =============================================================================
# 방법 2: 상태공간모형 (Local Linear Trend + Seasonal)
# =============================================================================
cat("/n/n========== 방법 2: 상태공간모형 ==========/n/n")

# 모형 구성: dlmModPoly(order=2) + dlmModSeas(frequency=4)
buildFun <- function(parm) {
  mod <- dlmModPoly(order = 2, 
                    dV = exp(parm[1]),
                    dW = c(exp(parm[2]), exp(parm[3])))
  mod <- mod + dlmModSeas(frequency = 4, 
                          dV = 0,
                          dW = c(exp(parm[4]), 0, 0))
  return(mod)
}

# MLE 추정
init_var <- var(sales_ts) / 100
init_parm <- rep(log(init_var), 4)

fit_dlm <- dlmMLE(sales_ts, 
                  parm = init_parm, 
                  build = buildFun,
                  control = list(maxit = 500))

cat("MLE 수렴 상태:", fit_dlm$convergence, "(0이면 성공)/n")
cat("추정된 분산 파라미터:/n")
estimated_vars <- exp(fit_dlm$par)
names(estimated_vars) <- c("sigma2_eps (관측)", "sigma2_a (수준)", 
                           "sigma2_b (추세)", "sigma2_s (계절)")
print(round(estimated_vars, 2))

# 칼만 필터링 + 예측
fitted_mod <- buildFun(fit_dlm$par)
filtered <- dlmFilter(sales_ts, fitted_mod)
forecast_dlm <- dlmForecast(filtered, nAhead = 4)

pred_mean <- as.numeric(forecast_dlm$f)
pred_sd <- sqrt(sapply(forecast_dlm$Q, function(x) x[1,1]))

# 음수 보정 + 95% 신뢰구간
pred_mean_pos <- pmax(pred_mean, 0)
lower_95 <- pmax(pred_mean - 1.96 * pred_sd, 0)
upper_95 <- pred_mean + 1.96 * pred_sd

result_dlm <- data.frame(
  Quarter = names(actual_2024),
  Point_Forecast = round(pred_mean_pos, 0),
  Lo_95 = round(lower_95, 0),
  Hi_95 = round(upper_95, 0)
)
cat("/n2024년 예측 (상태공간모형):/n")
print(result_dlm)


# =============================================================================
# 실제값과 비교 — 진짜 예측력 검증!
# =============================================================================
cat("/n/n========== 실제 2024년 값과 비교 ==========/n/n")

# 실제 2024년 값
actual_2024 <- c(119600, 90800, 85800, 94900)
names(actual_2024) <- c("2024 Q1", "2024 Q2", "2024 Q3", "2024 Q4")

arima_pred <- as.numeric(forecast_arima$mean)
dlm_pred <- pred_mean_pos

# 비교 표
comparison <- data.frame(
  Quarter = names(actual_2024),
  Actual = actual_2024,
  SARIMA = round(arima_prㅠed, 0),
  SARIMA_Err = round(actual_2024 - arima_pred, 0),
  StateSpace = round(dlm_pred, 0),
  SS_Err = round(actual_2024 - dlm_pred, 0)
)
cat("예측 vs 실제 비교 표:/n")
print(comparison, row.names = FALSE)

# 성능 평가
evaluate <- function(actual, pred, name) {
  mae  <- mean(abs(actual - pred))
  rmse <- sqrt(mean((actual - pred)^2))
  mape <- mean(abs((actual - pred) / actual)) * 100
  cat(sprintf("  %s -- MAE: %7.0f,  RMSE: %7.0f,  MAPE: %5.2f%%/n",
              name, mae, rmse, mape))
}

cat("/n예측 성능 지표:/n")
evaluate(actual_2024, arima_pred, "SARIMA      ")
evaluate(actual_2024, dlm_pred,   "State-Space ")

arima_rmse <- sqrt(mean((actual_2024 - arima_pred)^2))
dlm_rmse <- sqrt(mean((actual_2024 - dlm_pred)^2))
cat("/n>> RMSE 기준 더 좋은 모형:", 
    ifelse(arima_rmse < dlm_rmse, "SARIMA", "State-Space"), "/n")

# 95% 신뢰구간 적중 여부
arima_lo <- as.numeric(forecast_arima$lower[, "95%"])
arima_hi <- as.numeric(forecast_arima$upper[, "95%"])
in_arima_ci <- actual_2024 >= arima_lo & actual_2024 <= arima_hi
in_dlm_ci   <- actual_2024 >= lower_95 & actual_2024 <= upper_95

cat("/n95% 신뢰구간 안에 실제값이 들어갔는지:/n")
cat("  SARIMA      :", paste(in_arima_ci, collapse=" / "), 
    "  -> ", sum(in_arima_ci), "/4/n")
cat("  State-Space :", paste(in_dlm_ci, collapse=" / "),
    "  -> ", sum(in_dlm_ci), "/4/n")


# =============================================================================
# 종합 시각화: 전체 시계열 + 두 모형 예측 + 실제값
# =============================================================================
all_quarters <- seq(from = as.Date("2015-01-01"), 
                    by = "quarter", 
                    length.out = 40)

plot_df <- data.frame(
  Date = all_quarters,
  Train = c(as.numeric(sales_ts), rep(NA, 4)),
  Actual_2024 = c(rep(NA, 36), actual_2024),
  SARIMA = c(rep(NA, 36), arima_pred),
  StateSpace = c(rep(NA, 36), dlm_pred)
)

p1 <- ggplot(plot_df, aes(x = Date)) +
  geom_line(aes(y = Train, color = "Training (2015-2023)"), size = 1) +
  geom_point(aes(y = Train, color = "Training (2015-2023)"), size = 1.5) +
  geom_line(aes(y = Actual_2024, color = "Actual 2024"), size = 1.3) +
  geom_point(aes(y = Actual_2024, color = "Actual 2024"), 
             size = 4, shape = 18) +
  geom_line(aes(y = SARIMA, color = "SARIMA forecast"), 
            size = 1.1, linetype = "dashed") +
  geom_point(aes(y = SARIMA, color = "SARIMA forecast"), size = 3) +
  geom_line(aes(y = StateSpace, color = "State-Space forecast"), 
            size = 1.1, linetype = "dotted") +
  geom_point(aes(y = StateSpace, color = "State-Space forecast"), size = 3) +
  scale_color_manual(values = c("Training (2015-2023)" = "gray40",
                                "Actual 2024" = "black",
                                "SARIMA forecast" = "steelblue",
                                "State-Space forecast" = "tomato")) +
  labs(title = "Apple 분기별 매출: 두 모형 예측 vs 실제 2024",
       subtitle = "Training: 36분기 / Test: 2024 Q1-Q4 (실제 119600/90800/85800/94900)",
       x = "연도", y = "매출액 (백만 달러)", color = "") +
  theme_minimal(base_size = 12) +
  theme(legend.position = "bottom")
print(p1)
