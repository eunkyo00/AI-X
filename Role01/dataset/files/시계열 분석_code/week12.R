#install.packages("MASS")
library(MASS)

F1 <- matrix(c(1,1,0,1),2,2, byrow=T) #상태전이행렬 
H <- matrix(c(1,0),1,2)  #관측행렬
Q <- diag(c(0.25,0.09))   #상태 잡음 공분산(수준변화 잡음 분산, 기울기변화 잡음 분산 )
R <- 1.44  # 관측 잡음 분산 

P <- diag(2)  #예측 공분산 변수 초기화 
for(i in 1:2000){
  pp <- F1%*%P%*%t(F1) + Q  #한 스텝 앞선 예측 공분산
  S <- H%*%pp%*%t(H) + R #잔차 분산 (예측값과 실제 관측 간 차이의 분산)
  K <- pp%*%t(H)%*%solve(S)  #예측치와 관측치를 얼마나 섞어 최종 추정치를 만들지 결정하는 가중치 
  P <- (diag(2) - K%*%H) %*% pp  #업데이트 된 상태 추정의 불확실성 계산
}
P #수렴된 예측 공분산 
K #수렴된 칼만 이득 

p_ss <- P[1,1]  #variance of level
r_ss <- P[1,2]  #covariance of level & slope 
q_ss <- P[2,2]  #variance of slope (trend)
kmu_ss <- K[1,1]  #K^mu
kbeta_ss <- K[2,1]  #K^beta

y <- c(2.5,3.1,2.8,1.9,2.2,2.9)
year <- 2010:2015

l0 <- 2
m0 <- 0
x <- matrix(c(l0,m0),2,1)

lt <- numeric(length(y))
mt <- numeric(length(y))

for(t in 1:length(y)){
  x_pred <- F1%*%x  #상태전이행렬 * 직전 시점의 상태벡터 = 한 스텝 앞선 상태를 예측 
  y_pred <- H%*%x_pred #관측행렬 * 상태 예측값 = 관측값 예측 
  e <- y[t] - y_pred  #실제 관측치와 예측된 관측치와의 차이 = 잔차
  
  x <- x_pred+K%*%e  #상태 예측값 + 칼만이득*잔차 = 
                     #예측된 상태에 잔차를 곱한 보정값을 더해 최종 추정된 상태를 구함 
  
  lt[t] <- x[1]  #업데이트 된 상태 벡터의 수준 값
  mt[t] <- x[2]  #업데이트 된 상태 벡터의 추세 값
}
data.frame(year, y, lt, mt, p_ss, r_ss, q_ss, kmu_ss, kbeta_ss) #7

n_pred <- length(y)-1
years_pred <- 2011:2015
y_pred <- numeric(n_pred)
residual <- numeric(n_pred)

for(i in 1:n_pred){
  x_i <- matrix(c(lt[i],mt[i]),2,1)
  y_pred[i] <- as.numeric(H%*%(F1%*%x_i))
  residual[i] <- y[i+1]-y_pred[i]
}
results <- data.frame(Year=years_pred, Y=y[2:6], Forecast=round(y_pred,1), 
                      Residual=round(residual,1))
print(results)

mean(residual^2) #l0=1일 때 0.684, l0=2일때 0.477
