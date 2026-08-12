%% plot time series figure and calculate velocity simpally (fitting a straight line)
% modified by Cassandra Cabigan 09/2022
% 1 site with 1 offset
% to average the velocities
% separate text files into N files with filename_N
% LOOK FOR COMMENTS (ALL CAPS)

close all
clear

fid=fopen('123','r');
filename=fscanf(fid,'%s',[6 inf]); %open files: *NEU
fclose(fid);
filename=filename';
num_file=size(filename,1);

outvel=['Velocity_rover(regress)_10'];
fiddv=fopen(outvel,'w');
fprintf(fiddv,'%s\n','-----------------------------------------------------------------------');
fprintf(fiddv,'%s\n','sites        Ve                     Vn                    Vu   unit: mm');
fprintf(fiddv,'%s\n','-----------------------------------------------------------------------');

fig=figure;
    
for k=1:1:num_file
    
    files=filename(k,:);
    rawdata=load(files);
    t=rawdata(:,1);  
    d=rawdata(:,2:4);
    d(:,1)=d(:,1)-mean(d(:,1)); d(:,2)=d(:,2)-mean(d(:,2)); d(:,3)=d(:,3)-mean(d(:,3));
    sitename=files(1:4);e=d(:,1);n=d(:,2);u=d(:,3);
    d=d*100;  %m--> cm
    N=length(t);
    
    if N>=3
    residual=[];
    dhat=[];
    G = zeros(N,2); 
    G(:,1) = ones(N,1); 
    G(:,2) = t; 
    model=[];
    rsqrd=[];
   
    for iii=1:1:3
        model(1:2,iii)= G\d(:,iii); %least squares regression
        dhat(:,iii)=G*model(:,iii); %fitted y
        residual(:,iii)=d(:,iii)-dhat(:,iii); %residuals
        % rsqrd(1,iii)=1 - sum(residual(:,iii).^2)/sum((d(:,iii)-mean(d(:,iii))).^2);
        rsqrd(1,iii)=1 - sum(residual(:,iii).^2)/((length(d(:,iii))-1)*var(d(:,iii))); %r-squared
    end
    
    % varM = inv(G'*G);
    rnorm=[];sig_m=[];stt=[];rstd=[];
   
    for jjj=1:1:3
        rnorm(1,jjj)=sum(residual(:,jjj).^2)/(length(residual)-2);
        stt=sum((G(:,2)-mean(G(:,2))).^2);
        % sig_m(jjj)=sqrt(varM(2,2)*rnorm(jjj)); %in cm, standard error of a regression slope
        sig_m(1,jjj)=sqrt(rnorm(jjj)/stt); %in cm, standard error of a regression slope
        rstd(1,jjj)=sqrt(rnorm(jjj)); %in cm, residual std or standard error of the estimate
    end
    
    fprintf(fiddv,'%s %10.5f +- %4.1f    %10.5f +- %4.1f    %10.5f +- %4.1f\n',files,model(2,1)*10,sig_m(1)*10,model(2,2)*10,sig_m(2)*10,model(2,3)*10,sig_m(3)*10);
    % unit:mm (original data: unit=cm)
    
    Vf(k,:)=[model(2,1)*10 model(2,2)*10 model(2,3)*10];
    
    he=subplot(3,1,1);
    hold on
    plot(t,d(:,1),'o', 'MarkerSize', 3, 'MarkerEdgeColor', '#003399');
    plot(t,dhat(:,1)','g-', 'LineWidth', 0.7);
    ylabel('East (cm)');
    title(sitename, 'FontSize', 12);
    Ve=['V_',num2str(k),'=',num2str(model(2,1)*10,2),' mm/yr'];
    text(mean(t),mean(d(:,1))+1.5,Ve,'FontSize',6,'Color','#D95319'); % ADJUST TEXT POSITION -> text(x+-N,y+-N,Ve) where N>=0
    set(0,'defaultAxesFontSize',8);
    set(he,'linewidth',0.9,'box','on');
    hold off
    
    hn=subplot(3,1,2);
    hold on
    plot(t,d(:,2),'o', 'MarkerSize', 3, 'MarkerEdgeColor', '#003399');
    plot(t,dhat(:,2)','g-', 'LineWidth', 0.7);
    ylabel('North (cm)');
    Vn=['V_',num2str(k),'=',num2str(model(2,2)*10,2),' mm/yr'];
    text(mean(t),mean(d(:,2))-1.7,Vn,'FontSize',6,'Color','#D95319'); % ADJUST TEXT POSITION -> text(x+-N,y+-N,Vn) where N>=0
    set(0,'defaultAxesFontSize',8);
    set(hn,'linewidth',0.9,'box','on');
    hold off
    
    hu=subplot(3,1,3);
    hold on
    plot(t,d(:,3),'o', 'MarkerSize', 3, 'MarkerEdgeColor', '#003399');
    plot(t,dhat(:,3)','g-', 'LineWidth', 0.7);
    ylabel('Up (cm)');
    xlabel('TIME');
    Vu=['V_',num2str(k),'=',num2str(model(2,3)*10,2),' mm/yr'];
    text(mean(t),mean(d(:,3))-4,Vu,'FontSize',6,'Color','#D95319'); % ADJUST TEXT POSITION -> text(x+-N,y+-N,Vu) where N>=0
    set(0,'defaultAxesFontSize',8);
    set(hu,'linewidth',0.9,'box','on');
    hold off
    
    end 
end

    he=subplot(3,1,1);
    Vef=['V=',num2str(round(mean(Vf(:,1)))),' mm/yr'];
    annotation('textbox',[0.76 0.87 0.135 0.035],'String',Vef,'FontSize',7, 'BackgroundColor','white','FaceAlpha',0.8, 'Margin',3);
    
    hn=subplot(3,1,2);
    Vnf=['V=',num2str(round(mean(Vf(:,2)))),' mm/yr'];
    annotation('textbox',[0.76 0.57 0.135 0.035],'String',Vnf,'FontSize',7, 'BackgroundColor','white','FaceAlpha',0.8, 'Margin',3);
    
    hu=subplot(3,1,3);
    Vuf=['V=',num2str(round(mean(Vf(:,3)))),' mm/yr'];
    annotation('textbox',[0.76 0.27 0.135 0.035],'String',Vuf,'FontSize',7, 'BackgroundColor','white','FaceAlpha',0.8, 'Margin',3);
    
    mdt=num2str(max(t));
    mdt=[mdt(1:4),' ',num2str(round(str2num(mdt(5:9))*365.25))];
    ltm=['Last observation (yyyy doy): ' num2str(mdt)];
    annotation('textbox',[0.13 0.0001 0.5 0.04],'String',ltm,'EdgeColor','none','FontSize',6);
    
    datenow=datetime('now');
    dn=['Plotted on ' datestr(datenow) ' by MOVE Faults'];
    annotation('textbox',[0.57 0.0001 0.5 0.04],'String',dn,'EdgeColor','none','FontSize',6);

    print('-djpeg','-r300',[sitename]);
    close all;
    
fclose(fiddv);