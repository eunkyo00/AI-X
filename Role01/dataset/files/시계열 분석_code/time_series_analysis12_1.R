library(MASS)

# 1) 모델파라미터
F1 <- matrix(c(1,1,0,1), 2, 2, byrow=T)
H <- matrix(c(1,0), 1, 2)
Q <- diag(c(9,4))   # σ_a^2 = 9, σ_b^2 = 4
R <- 25            # σ_ε^2 = 25

# 2) Riccati 반복으로 steady‐state P, K 구하기
P <- diag(2)  # 초기값(무엇이든양의정부호면OK)    
for(i in 1:2000){
  Pp <- F1 %*% P %*% t(F1) + Q   # (a) 공분산예측             
  S  <-H %*% Pp %*% t(H) + R    #     잔차분산           
  K  <-Pp %*% t(H) %*% solve(S)   # (b) 칼만이득         
  P  <-(diag(2) - K %*% H) %*% Pp   # (c) 공분산업데이트       
}
P_ss <- P    # 수렴된예측공분산P_{t|t-1}
K_ss <- K    # 수렴된칼만이득

# 3) steady‐state 값 확인
p_ss <- P_ss[1,1]    # Var(level)
r_ss <- P_ss[1,2]    # Cov(level,slope)
q_ss <- P_ss[2,2]    # Var(slope)
Kmu_ss <- K_ss[1,1]    # K^μ
Kbeta_ss<- K_ss[2,1]    # K^β

data.frame(p_ss, r_ss, q_ss, Kmu_ss, Kbeta_ss)

x <- matrix(c(l0, m0), 2, 1)   # 초기 상태 벡터
for (t in 1:length(y)) {     #y: 데이터
  x_pred <- F1 %*% x   # 예측단계
  y_pred <- H %*% x_pred # 측정값예측및오차계산
  e <- y[t] - y_pred
  x <- x_pred + K_ss %*% e # 정상상태칼만이득을사용한상태업데이트
  lt[t] <- x[1]
  mt[t] <- x[2]
}

data.frame(years,  y, lt, mt)