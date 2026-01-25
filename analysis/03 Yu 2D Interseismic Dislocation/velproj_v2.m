% Project velocity vectors in the specified direction
%
% Yaju Hsu  02/25/02
% 
% Date                        Change/s
% 06/02/22  Cassandra Cabigan change plots and create output files                
%
% have to change Az, the origin according to your need
% Az start from North, clockwise is +          

% input format (PHm.prn)
% Site, E coord, N coord, Height, Velocity, Azi, Vu, Height_err, E_err,  N_err

 clear

 filename=input('Input data file --- ','s' );
 Az=input('Direction of projection (start from N, CW is + (0-180) --- '); % unit "degree
 ref=input('The coordinate of the reference station ---  [E, N] ');
 fault=input('The coordinate of the fault --- [E, N] '); %location of fault
 width=input('The width of the profile ---(km) ');

 fileID=fopen(filename);
 C=textscan(fileID,'%s %f %f %*f %f %f %f %f %f %f', 'headerlines',1); % skip 4th column
 fclose(fileID);
 [sites, E, N, Vel, azi, Vu, sn, se, su] = C{:};
 %[sites, E, N, Vel, azi, Vu, sn, se, su]=textread(filename,'%s%f%f%*f%f%f%f%f%f%f','headerlines',1);
  
% read sites	
  sites=char(sites);
  deg2rad=pi/180;
   
% components of  parallel to projection direction (East is positive)
 ang=azi-Az;
 Eerr=se*1; % 95% confidence 
 Nerr=su*1;
 err=sqrt(Eerr.^2+Nerr.^2);
 Vpall=Vel.*cos(ang*deg2rad);
 errp=abs(err.*cos(ang*deg2rad));
 Vortho=-Vel.*sin(ang*deg2rad);
 erro=abs(err.*sin(ang*deg2rad));
 
% estimate distances from reference station
 theta=Az*deg2rad;
 y1=-[E; ref(1)]*cos(theta)+[N; ref(2)]*sin(theta); % perpendicular to projected direction
 x1=[E; ref(1)]*sin(theta)+[N; ref(2)]*cos(theta); % parallel to projected direction
 y2=-[fault(1); ref(1)]*cos(theta)+[fault(2); ref(2)]*sin(theta);
 x2=[fault(1); ref(1)]*sin(theta)+[fault(2); ref(2)]*cos(theta);
 disty=(y1-y1(end))/1000; % km
 distx=(x1-x1(end))/1000; % km
 distfy=(y2-y2(end))/1000; % km
 distfx=(x2-x2(end))/1000; % km
 disty=disty(1:end-1);
 distx=distx(1:end-1);
 distfy=distfy(1:end-1);
 distfx=distfx(1:end-1);
 % zone =width*2  (km)
 com=find(abs(disty)<=width);
 % northern profile site74, dist<=35, offset 94.37 km
 [dis0,I]=sort(distx(com));
 
% parallel components
 figure
 %subplot(2,2,1)
 plot(dis0,Vpall(com(I)),'ko-','LineWidth',1)
 hold on
 errorbar(dis0,Vpall(com(I)),errp(com(I)),'ro','LineWidth',1)
 text(dis0,Vpall(com(I)),sites(com(I),1:4),'fontsize',10)
 xline(distfx,'b--',{'fault'})
 xlabel('km','fontsize',12)
 ylabel('V_h fault-perpendicular (mm/yr)','fontsize',12);
 title(['Parallel to N',num2str(Az),' deg direction'],'fontsize',8)
 %xlim([-60,20])

% perpendicular components
 figure
 %subplot(2,2,2)
 plot(dis0,Vortho(com(I)),'ko-','LineWidth',1)
 hold on
 errorbar(dis0,Vortho(com(I)),erro(com(I)),'ro','LineWidth',1)
 xline(distfx,'--b',{'fault'})
 text(dis0+1,Vortho(com(I)),sites(com(I),1:4),'fontsize',10)
 xlabel('km','fontsize',12)
 ylabel('V_h fault-parallel (mm/yr)','fontsize',12);
 title(['Perpendicular to N',num2str(Az),' deg direction'],'fontsize',8)
 %xlim([-60,20])
 
% vertical components
 figure
 %subplot(2,2,3)
 plot(dis0,Vu(com(I)),'ko-','LineWidth',1)
 hold on
 errorbar(dis0,Vu(com(I)),su(com(I)),'o','LineWidth',1)
 text(dis0,Vu(com(I)),sites(com(I),1:4),'fontsize',10)
 hold on
 xlabel('km','fontsize',12)
 ylabel('Vu (mm/yr)','fontsize',12);
 title('Vertical velocity (mm/yr)','fontsize',8)
 %xlim([-60,20])

 figure
 plot(E,N,'k.')
 hold on
 plot(E(com(I)),N(com(I)),'r^', 'MarkerFaceColor', 'red')
 text(E(com(I)),N(com(I)),sites(com(I),1:4),'fontsize',10)
 axis('equal')
 
 Vpall=Vpall(com(I));
 err=erro(com(I));
 sites=sites(com(I),1:4);

 Vorth=Vortho(com(I));
 errp=errp(com(I));
 
 save 2D_PH dis0 Vorth err sites
 
 dispx = sprintf('Distance of fault from reference point: %f', distfx);
 disp(dispx)
 
 fid = fopen('projected_vel.txt','w');
 fprintf(fid,'%5s %12s %12s %12s %12s %8s %8s %8s\n','sites', 'distance', 'Vhfault_p', 'Vhfault_o', 'Vfault_v', 'sigma_p', 'sigma_o', 'sigma_u');
 for i=1:8
    fprintf(fid,'%5s %12.6f %12.5f %12.5f %12.5f %8.2f %8.2f %8.2f\n', sites(i,:), dis0(i,1), Vorth(i,1), Vpall(i,1), Vu(i,1), err(i,1), errp(i,1), su(i,1));
 end
 fclose(fid);