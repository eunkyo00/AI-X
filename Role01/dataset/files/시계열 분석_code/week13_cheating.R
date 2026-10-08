library(dlm)
library(MASS)
y <- c(8,10,-9,13,-5,-15,24,6,-21,20,-7,-24)

buildFun2 <- function(par){
  theta <- par[1] #MA(1) 계수 theta 
  sigma2 <- exp(par[2]) #로그 변환된 분산을 원래 분산 s^2 역변환
  FF <- matrix(c(1,-theta), nrow=1) #관측 방정식 행렬
  V <- 0 #관측오차 분산 
  GG <- matrix(c(0,0,1,0), nrow=2, byrow=T) #상태 전이 행렬 
  W <- matrix(c(sigma2, 0, 0, 0), nrow=2) #상태 잡음 공분산 행렬
  dlm(FF=FF, V=V, GG=GG, W=W, m0=c(0,0), C0=W)
}

initPar <- c(0.85, log(var(y))) #초기 파라미터터 설정
fit_dlm <- dlmMLE(y, parm=initPar, build=buildFun2) 
#MLE로 최적의 theta, log(sig^2) 찾음

theta_hat <- fit_dlm$par[1]
sigma2_hat <- exp(fit_dlm$par[2])

cat("theta=", round(theta_hat,3),'\n')
cat("sigma^2=", round(sigma2_hat,3),'\n')

F1 <- matrix(c(1,1,0,1),2,2, byrow=T)
H <- matrix(c(1,0),1,2)
Q <- diag(c(9,4))
R <- 25

P <- diag(2)
for(i in 1:2000){
  pp <- F1 %*%P %*% t(F1) + Q  #공분산 예측
  S <- H %*% pp %*% t(H) + R  #잔차 분산
  K <- pp %*% t(H) %*% solve(S) #칼만 이득
  P <- (diag(2)-K%*%H) %*% pp #공분산 업데이트
}
P_ss <- P #수렴된 예측 공분산
K_ss <- K #수렴된 칼만 이득 

p_ss <- P_ss[1,1]  #variance of level
r_ss <- P_ss[1,2]  #covariance of level & slope 
q_ss <- P_ss[2,2]  #variance of slope (trend)
kmu_ss <- K_ss[1,1]  #K^mu
kbeta_ss <- K_ss[2,1]  #K^beta

data.frame(p_ss,r_ss,q_ss,kmu_ss,kbeta_ss)

#data
y <- c(1571.5,1669,1411.2,1266.4,1160.1,1250.8)
years <- 2011:2016

#initialization
l0 <- 1100
m0 <- 150
x <- matrix(c(l0,m0),2,1)

lt <- numeric(length(y))
mt <- numeric(length(y))
for(t in 1:length(y)){
  x_pred <- F1 %*% x  #예측단계 
  y_pred <- H%*%x_pred #측정값 예측
  e <- y[t] - y_pred #오차 계산
  
  x<- x_pred + K_ss%*%e #정상상태 칼만 이득을 사용한 상태 업데이트
  
  lt[t] <- x[1]
  mt[t] <- x[2]
}
data.frame(year, y, lt, mt)

n_pred <- length(y) - 1
years_pred <- 2012:2016
y_pred <- numeric(n_pred) #예측값 저장
residual <- numeric(n_pred) #잔차 저장 

for(i in 1:n_pred) {
  x_i <- matrix(c(lt[i], mt[i]),2,1)
  y_pred[i] <- as.numeric(H%*%(F1%*%x_i))
  residual[i] <- y[i+1] - y_pred[i]
}
data.frame(Year=years_pred, Y=y[2:6], Forecast=round(y_pred,1), 
           Residual=round(residual,1))

##############week13 assignment #######
F1 <- matrix(c(1,1,0,1),2,2, byrow=T)
H <- matrix(c(1,0),1,2)
Q <- diag(c(0.25,0.09))
R <- 1.44

P <- diag(2)
for(i in 1:2000){
  pp <- F1 %*%P %*% t(F1) + Q  #공분산 예측
  S <- H %*% pp %*% t(H) + R  #잔차 분산
  K <- pp %*% t(H) %*% solve(S) #칼만 이득
  P <- (diag(2)-K%*%H) %*% pp #공분산 업데이트
}
P_ss <- P #수렴된 예측 공분산
K_ss <- K #수렴된 칼만 이득 

p_ss <- P_ss[1,1]  #variance of level
r_ss <- P_ss[1,2]  #covariance of level & slope 
q_ss <- P_ss[2,2]  #variance of slope (trend)
kmu_ss <- K_ss[1,1]  #K^mu
kbeta_ss <- K_ss[2,1]  #K^beta

data.frame(p_ss,r_ss,q_ss,kmu_ss,kbeta_ss)

#data
y <- c(2.5,3.1,2.8,1.9,2.2,2.9)
years <- 2010:2015

#initialization
l0 <- 1
m0 <- 0
x <- matrix(c(l0,m0),2,1)

lt <- numeric(length(y))
mt <- numeric(length(y))
for(t in 1:length(y)){
  x_pred <- F1 %*% x  #예측단계 
  y_pred <- H%*%x_pred #측정값 예측
  e <- y[t] - y_pred #오차 계산
  
  x<- x_pred + K_ss%*%e #정상상태 칼만 이득을 사용한 상태 업데이트
  
  lt[t] <- x[1]
  mt[t] <- x[2]
}
data.frame(year, y, lt, mt)

n_pred <- length(y) - 1
years_pred <- 2011:2015
y_pred <- numeric(n_pred) #예측값 저장
residual <- numeric(n_pred) #잔차 저장 

for(i in 1:n_pred) {
  x_i <- matrix(c(lt[i], mt[i]),2,1)
  y_pred[i] <- as.numeric(H%*%(F1%*%x_i))
  residual[i] <- y[i+1] - y_pred[i]
}
data.frame(Year=years_pred, Y=y[2:6], Forecast=round(y_pred,1), 
           Residual=round(residual,1))
mean(residual^2) #mse
