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
    
 
% Input block velocity
block_motion=input('Input block motion (mm/yr): ');

% Find stations to the east of the reference station
com=find(xy(:,1)>=0);
d=Vorth;
% Back_slip=Interseismic velocity-Block motion   
d(com)=Vorth(com)-block_motion;

% Input fault parameters
% middle point of the fault
E1=input('Input east offset of midpoint from origin (km): ');
N1=input('Input north offset of midpoint from origin (km): ');
D=input('Input fault top depth (km): ');
dip1=input('Input dip angle (degrees): ');
W=input('Input fault width in dip direction (km): ');

%           [ Length, Wid,  Dep,   Dip,  strike,  E,  N]
faults(1,:)=[ 1000     W    D   -180+dip1   0    E1   N1];

dis_geom=[faults, [1 1 0]];
    
% Plot station locations as points
        figure
        plot(xy(:,1),xy(:,2),'ro'),axis('equal')
        text(xy(:,1),xy(:,2),sites,'fontsize',8)
        hold on

        [nf, ten]=size(dis_geom);
        for i=1:nf
         displot(dis_geom(i,:))
        end
        title('Geometry in Local Cartesian Coordinates'),drawnow
        axis('tight')
 
        
 %% Setup Fault Geometry and Smoothing operators
        nhe1 =1; nve1 = 1;
        pm1 =patchfault(dis_geom(1,1:7),nhe1,nve1);
        pm1ss = [pm1 ones(size(pm1(:,1))) zeros(size(pm1(:,1))) zeros(size(pm1(:,1)))];
        pm1ds = [pm1 zeros(size(pm1(:,1))) ones(size(pm1(:,1))) zeros(size(pm1(:,1)))];

        pm = (pm1);


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


% Residuals
dhat = G11*s;
r =d-dhat;
chi2=sum( (r.^2)./diag(dcov)) ;
r_chi2=chi2/length(r);
wrms=sqrt( r'*inv(dcov)*r / trace(inv(dcov)) );

figure
h=axes;
set(h,'box','on','linewidth',1.5,'fontsize',12)
hold on
title('Back slip ','fontsize',14)
plot(xy(:,1),d,'k.-','markersize',20,'linewidth',1.3)
plot(xy(:,1),dhat,'r.-','markersize',20,'linewidth',1.3)
text(xy(:,1), d+3, sites,'fontsize',10)
hold on
legend('Obs','Pred','o')
cc=errorbar(xy(:,1),d,err,'k.');
set(cc,'markersize',15)
set(get(get(cc,'Annotation'),'LegendInformation'),'IconDisplayStyle','off');
xlabel('Distance (km)')
ylabel('V_p_a_l_l (mm/yr)')
ff=plot([E1; E1],[-30; 40],'k-','linewidth',2);
set(get(get(ff,'Annotation'),'LegendInformation'),'IconDisplayStyle','off');
text(E1+5,10, [num2str(s/1,2),' mm/yr'])


% Find stations to the east of the reference station
com=find(xy(:,1)>=0);
d=Vorth;
% Back_slip=Interseismic velocity-Block motion
dhat(com)=dhat(com)+block_motion;

figure
h=axes;
set(h,'box','on','linewidth',1.5,'fontsize',12)
hold on
title('Interseismic Velocity ','fontsize',14)
plot(xy(:,1),d,'k.-','markersize',20,'linewidth',1.3)
plot(xy(:,1),dhat,'r.-','markersize',20,'linewidth',1.3)
text(xy(:,1), d+3, sites,'fontsize',10)
hold on
legend('Obs','Pred','o')
ee=errorbar(xy(:,1),d,err,'kd');
set(get(get(ee,'Annotation'),'LegendInformation'),'IconDisplayStyle','off');
xlabel('Distance (km)')
ylabel('V_p_a_l_l (mm/yr)')
ll=plot([E1; E1],[-10; 50],'k-','linewidth',2);
set(get(get(ll,'Annotation'),'LegendInformation'),'IconDisplayStyle','off');
text(E1+5,10, [num2str(s/1,2),' mm/yr'])
