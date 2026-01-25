%% plot time series figure and calculate velocity simpally (fitting a straight line)%%
% modified by Cassandra Cabigan 07/2022
% added/changed some statistics and plots

close all
clear

fid=fopen('123','r');
filename=fscanf(fid,'%s',[4 inf]); %open files: *NEU
fclose(fid);
filename=filename';
num_file=size(filename,1);

outvel=['Velocity_rover(regress)_10'];
fiddv=fopen(outvel,'w');
fprintf(fiddv,'%s\n','-----------------------------------------------------------------------');
fprintf(fiddv,'%s\n','sites        Ve                     Vn                    Vu   unit: mm');
fprintf(fiddv,'%s\n','-----------------------------------------------------------------------');


for k=1:1:num_file
    
    files=filename(k,:);
    rawdata=load(files);
    t=rawdata(:,1);  
    d=rawdata(:,2:4);
    d(:,1)=d(:,1)-mean(d(:,1)); d(:,2)=d(:,2)-mean(d(:,2)); d(:,3)=d(:,3)-mean(d(:,3));
    sitename=files;e=d(:,1);n=d(:,2);u=d(:,3);
    d=d*100;  %m--> cm
    N=length(t);
   
    %[t,e,n,u,bd]=rm_average_n(t,e,n,u,100,4,30);% moving average new
    %[t,e,n,u,badn]=rm_outlier(t,e,n,u,4)
    
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
    
    mstd=[];
    for kkk=1:1:3
        %mstd(:,kkk)=movstd(d(:,kkk),length(d(:,kkk))); %moving standard deviation
        mstd(:,kkk)=movstd(d(:,kkk),365); %1-year-mstd
    end
    
    fprintf(fiddv,'%s %10.5f +- %4.1f    %10.5f +- %4.1f    %10.5f +- %4.1f\n',files,model(2,1)*10,sig_m(1)*10,model(2,2)*10,sig_m(2)*10,model(2,3)*10,sig_m(3)*10);
    % unit:mm (original data: unit=cm)
    
    figure;
    he=subplot(3,1,1);
    eeb=errorbar(t,d(:,1),mstd(:,1));
    eeb.LineStyle='none';
    eeb.CapSize=2;
    eeb.Color='#B0E0E6';
    hold on
    plot(t,d(:,1),'o', 'MarkerSize', 3, 'MarkerEdgeColor', '#003399');
    hold on
    plot(t,dhat(:,1)','g-', 'LineWidth', 0.7);
    hold off
    ylabel('East (cm)');
    title(sitename, 'FontSize', 12);
    % legend(['V=',num2str(model(2,1)*10,2),' mm/yr']);
    Ve=['V=',num2str(model(2,1)*10,2),' mm/yr'];
    annotation('textbox',[0.76 0.87 0.135 0.035],'String',Ve,'FontSize',7, 'BackgroundColor','white','FaceAlpha',0.8, 'Margin',3);
    % set(he,'linewidth',1.2,'box','on','fontsize',8);
    set(0,'defaultAxesFontSize',8);
    set(he,'linewidth',0.9,'box','on');
    
    hn=subplot(3,1,2);
    enb=errorbar(t,d(:,2),mstd(:,2));
    enb.LineStyle='none';
    enb.CapSize=2;
    enb.Color='#B0E0E6';
    hold on
    plot(t,d(:,2),'o', 'MarkerSize', 3, 'MarkerEdgeColor', '#003399');
    hold on
    plot(t,dhat(:,2)','g-', 'LineWidth', 0.7);
    hold off
    ylabel('North (cm)');
    % gtext(['V=' num2str(model(2,2)*10,2) ' cm/yr']);
    Vn=['V=',num2str(model(2,2)*10,2),' mm/yr'];
    annotation('textbox',[0.76 0.57 0.135 0.035],'String',Vn,'FontSize',7, 'BackgroundColor','white','FaceAlpha',0.8, 'Margin',3);
    % legend(['V=' num2str(model(2,2)*10,2) ' mm/yr']);
    % set(hn,'linewidth',1.2,'box','on','fontsize',8);
    set(0,'defaultAxesFontSize',8);
    set(hn,'linewidth',0.9,'box','on');
    
    hu=subplot(3,1,3);
    eub=errorbar(t,d(:,3),mstd(:,3));
    eub.LineStyle='none';
    eub.CapSize=2;
    eub.Color='#B0E0E6';
    hold on
    plot(t,d(:,3),'o', 'MarkerSize', 3, 'MarkerEdgeColor', '#003399');
    hold on
    plot(t,dhat(:,3)','g-', 'LineWidth', 0.7);
    hold off
    ylabel('Up (cm)');
    xlabel('TIME');
    % gtext(['V=' num2str(model(2,3)*10,2) ' cm/yr']);
    Vu=['V=',num2str(model(2,3)*10,2),' mm/yr'];
    annotation('textbox',[0.76 0.27 0.135 0.035],'String',Vu,'FontSize',7, 'BackgroundColor','white','FaceAlpha',0.8, 'Margin',3);
    % legend(['V=' num2str(model(2,3)*10,2) ' mm/yr']);
    % set(hu,'linewidth',1.2,'box','on','fontsize',8);
    set(0,'defaultAxesFontSize',8);
    set(hu,'linewidth',0.9,'box','on');
    
    mdt=sprintf('%0.4f',max(t));
    mdt=[mdt(1:4),' ',num2str(round(str2num(mdt(5:9))*365.25))];
    ltm=['Last observation (yyyy doy): ' num2str(mdt)];
    annotation('textbox',[0.13 0.0001 0.5 0.04],'String',ltm,'EdgeColor','none','FontSize',6);
    
    datenow=datetime('now');
    dn=['Plotted on ' datestr(datenow) ' by MOVE Faults'];
    annotation('textbox',[0.57 0.0001 0.5 0.04],'String',dn,'EdgeColor','none','FontSize',6);
    
    %print('-djpeg','-r300',[sitename '_rmc']);
    print('-djpeg','-r300',[sitename]);
    close all;
    end 
end

fclose(fiddv);