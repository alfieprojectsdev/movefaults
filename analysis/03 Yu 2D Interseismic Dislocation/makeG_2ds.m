clear all
warning off
TIME=cputime;


%% load Data
  	load  2D_PH
% Remove first station    
    Vorth=Vorth(2:end);
    dis0=dis0(2:end);
    sites=sites(2:end,:);
    err=err(2:end);
    dcov=diag(err.^2);
    
	Nsites = size(sites,1);
	xy = [dis0 dis0*0];
    
    

East=[];
Dep=[];
Wid=[];
Dip=[];
Resid=[];
Rate=[];

for E1=-10:1:-1
%for D=0:1:10
for W=5:2:20    
%for dip1=70:5:80    
for block_motion=30:2:50

% Input fault parameters
% middle point of the fault    
%E1=-5;
N1=0;
D=0;
dip1=80;



com=find(xy(:,1)>=0);
d=Vorth;
d(com)=Vorth(com)-block_motion;


%            [ Length, Wid,  Dep,   Dip,  strike,  E,  N]
faults(1,:)=[1000  W    D -180+dip1  0  E1  N1];

dis_geom = [faults, [1 0 0]];
    

        
 %% Setup Fault Geometry and Smoothing operators
        nhe1 =1; nve1 = 1;
        pm1 =patchfault(dis_geom(1,1:7),nhe1,nve1);
        pm1ss = [pm1 ones(size(pm1(:,1))) zeros(size(pm1(:,1))) zeros(size(pm1(:,1)))];
        pm1ds = [pm1 zeros(size(pm1(:,1))) ones(size(pm1(:,1))) zeros(size(pm1(:,1)))];
  

%% Compute Kernel for distributed slip calculation
        nu = 0.25;
 
         for i=1:size(pm1ss,1)
          tmp1 = disloc(pm1ss(i,:)', xy', nu);
          tmp2 = disloc(pm1ds(i,:)', xy', nu);
          G11(:,i)=tmp1(:);
          G12(:,i)=tmp2(:);
       end

   
     
 % Only take north component of Green functions      
      G11=G11(2:3:end);
        
 % C is the weigting matrix    
     C=inv(chol(dcov));
     
% Inversion
    s=(C*G11)\(C*d);
%s=fnnls(A'*A,A'*data);



% residuals
dhat = G11*s;
r =d-dhat;
chi2=sum( (r.^2)./diag(dcov)) ;
r_chi2=chi2/length(r);
wrms=sqrt( r'*inv(dcov)*r / trace(inv(dcov)) );


East=[East E1];
%Dep=[Dep D];
Wid=[Wid W];
%Dip=[Dip dip1];
Resid=[Resid wrms];
Rate=[Rate block_motion];
clear G11
end
end
end
%end
%end


figure
subplot(221)
plot(East,Resid,'r.')
xlabel('East'); ylabel('wrms')
grid on

subplot(222)
plot(Wid,Resid,'r.')
xlabel('Wid'); ylabel('wrms')
grid on

subplot(223)
plot(Rate,Resid,'r.')
xlabel('block motion'); ylabel('wrms')
grid on

