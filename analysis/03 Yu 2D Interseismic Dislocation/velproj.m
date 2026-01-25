% Project velocity vectors in the specified direction
%
% Yaju Hsu  02/25/02
% 
% Date                         Change
% 
% have to change Az, the origin according to your need
% Az start from North, clockwise is +          

% input format (vel.txt)
% Site, E coord, N coord, Height, Velocity, Azi, Vu, Height_err, E_err,  N_err


 filename=input('Input data file --- ','s' );
 Az=input('Direction of projection (start from N, CW is + (0-180) --- '); % unit "degree
 ref=input('The coordinate of the reference station ---  [x, y] ');
 width=input('The width of the profile ---(km) ');

 fileID=fopen(filename);
 C=textscan(fileID,'%s %f %f %*f %f %f %f %f %f %f', 'headerlines',1); % skip 4th column
 fclose(fileID);
 [sites, E, N, Vel, azi, Vu, sn, se, su] = C{:};
 %[sites, E, N, Vel, azi, Vu, sn, se, su]=textread(filename,'%s%f%f%*f%f%f%f%f%f%f','headerlines',1);
   
% read sites	
  sites=char(sites);
  deg2rad=pi/180;
   
% components of  parallel to projectin direction (East is positive)
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
 disty=(y1-y1(end))/1000; % km
 distx=(x1-x1(end))/1000; % km
 disty=disty(1:end-1);
 distx=distx(1:end-1);
 % zone =width*2  (km)
 com=find(abs(disty)<=width);
 % northern profile site74, dist<=35, offset 94.37 km
 [dis0,I]=sort(distx(com));
 
% parallel components
 figure
 %subplot(2,2,1)
 plot(dis0,Vpall(com(I)),'bo-')
 hold on
 errorbar(dis0,Vpall(com(I)),errp(com(I)),'o')
 text(dis0,Vpall(com(I)),sites(com(I),1:4),'fontsize',10)
 xlabel('km','fontsize',12)
 ylabel('Vh_p_a_l_l (mm)','fontsize',12);
 title(['Parallel to N',num2str(Az),' deg direction'],'fontsize',8)
 %xlim([-60,20])

% perpendicular components
 figure
 %subplot(2,2,2)
 plot(dis0,Vortho(com(I)),'r*-')
 hold on
 errorbar(dis0,Vortho(com(I)),erro(com(I)),'d')
 text(dis0+1,Vortho(com(I)),sites(com(I),1:4),'fontsize',10)
 xlabel('km','fontsize',12)
 ylabel('Vh_o_r_t_h (mm)','fontsize',12);
 title(['Perpendicular to N',num2str(Az),' deg direction'],'fontsize',8)
 %xlim([-60,20])
 
% vertical components
 figure
 %subplot(2,2,3)
 plot(dis0,Vu(com(I)),'k*-')
 hold on
 errorbar(dis0,Vu(com(I)),su(com(I)),'d')
 text(dis0,Vu(com(I)),sites(com(I),1:4),'fontsize',10)
 hold on
 xlabel('km','fontsize',12)
 ylabel('Vu (mm/yr)','fontsize',12);
 title('Vertical velocity (mm/yr)','fontsize',8)
 %xlim([-60,20])

 figure
 plot(E,N,'k.')
 hold on
 plot(E(com(I)),N(com(I)),'ro')
 axis('equal')
 
 Vorth=Vortho(com(I));
 err=erro(com(I));
 sites=sites(com(I),1:4);

 save 2D_PH dis0 Vorth err sites