clear variable
clear global
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
Slip=[];
Reduced_chi=[];
Chi=[];

for E1=-0.5:0.1:0.5
for N1=0
for D=0:1:5
for W=10:1:20    
for dip1=80:1:90 
for block_motion=25:1:35

% Input fault parameters
% middle point of the fault    
%E1=-5;
%N1=0;
%D=0;
%dipl=80;


com=find(xy(:,1)>=0);
d=Vorth;
d(com)=Vorth(com)-block_motion;


%           [ Length, Wid,  Dep,   Dip,  strike,  E,  N ]
faults(1,:)=[   1000   W     D  -180+dip1   0     E1  N1];

dis_geom = [faults, [1 1 0]];
    

        
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
          G11=tmp1(:);
          G12=tmp2(:);
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
Dep=[Dep D];
Wid=[Wid W];
Dip=[Dip dip1];
Resid=[Resid wrms];
Rate=[Rate block_motion];
Slip=[Slip s];
Reduced_chi=[Reduced_chi r_chi2];
Chi=[Chi chi2];
clear G11

end
end
end
end
end
end

Eastt=East';
Dept=Dep';
Widt=Wid';
Dipt=Dip';
Residt=Resid';
Ratet=Rate';
Slipt=Slip';
Reduced_chit=Reduced_chi';
Chit=Chi';

T = table(Eastt, Dept, Widt, Dipt, Residt, Ratet, Slipt, Reduced_chit, Chit, 'VariableNames', {'East','Depth','Width','Dip','Residual','Rate', 'Slip','Reduced chi2', 'Chi2'});
%fid = fopen('parameters.txt','a+');
writetable(T,'parameters.txt','Delimiter',' ');
%fclose(fid);

figure
subplot(231)
plot(East,Resid,'r.')
%plot(East,Residmin,'bs')
xlabel('East'); ylabel('wrms')
grid on

subplot(232)
plot(Wid,Resid,'r.')
%plot(Wid,Residmin,'bs')
xlabel('Width'); ylabel('wrms')
grid on

subplot(233)
plot(Rate,Resid,'r.')
%plot(Rate,Residmin,'bs')
xlabel('Block Motion'); ylabel('wrms')
grid on

subplot(234)
plot(Dep,Resid,'r.')
%plot(Dep,Residmin,'bs')
xlabel('Depth'); ylabel('wrms')
grid on

subplot(235)
plot(Dip,Resid,'r.')
%plot(Dip,Residmin,'bs')
xlabel('Dip'); ylabel('wrms')
grid on