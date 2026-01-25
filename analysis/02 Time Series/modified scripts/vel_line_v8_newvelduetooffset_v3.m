%% plot time series figure and calculate velocity simpally (fitting a straight line)
% modified by Cassandra Cabigan 11/2022
% 1 site with multiple offsets (1 SITE ONLY in "123")
% to average the velocities
% make text file with filename "1234"
% format: column 1 -> line number (start); column 2 -> line number (end)
% e.g. 1 500; 501 1000; 1001 2000
% LOOK FOR COMMENTS (ALL CAPS)

close all
clear

fid=fopen('123','r');
filename=fscanf(fid,'%s',[4 inf]); %open files: *NEU
fclose(fid);
filename=filename';
num_file=size(filename,1);

fid0=fopen('1234','r');
displaced=fscanf(fid0,'%i %i\n',[2 inf]); %open files: *NEU
fclose(fid0);
displaced=displaced';
num_file0=size(displaced,1);

outvel=['Velocity_rover(regress)_10'];
fiddv=fopen(outvel,'w');
fprintf(fiddv,'%s\n','-----------------------------------------------------------------------');
fprintf(fiddv,'%s\n','sites        Ve                     Vn                    Vu   unit: mm');
fprintf(fiddv,'%s\n','-----------------------------------------------------------------------');

fig=figure;

for k=1:1:num_file
    for kk=1:1:num_file0
        files=filename(k,:);
        rawdata=load(files);
        t=rawdata(:,1);
        d=rawdata(:,2:4);
        d(:,1)=d(:,1)-mean(d(:,1)); d(:,2)=d(:,2)-mean(d(:,2)); d(:,3)=d(:,3)-mean(d(:,3));
        sitename=files(1:4);
        d=d*100;  %m--> cm
    
        for N=length(displaced(kk,1):displaced(kk,2))
            residual=[];
            dhat=[];
            G=zeros(N,2);
            G(:,1)=ones(N,1);
            G(:,2)=t(displaced(kk,1):displaced(kk,2));
            model=[];
            rsqrd=[];
    
            for iii=1:1:3
                model(1:2,iii)= G\d(displaced(kk,1):displaced(kk,2),iii); %least squares regression
                dhat(:,iii)=G*model(:,iii); %fitted y
                residual(:,iii)=d(displaced(kk,1):displaced(kk,2),iii)-dhat(:,iii); %residuals
                % rsqrd(1,iii)=1 - sum(residual(:,iii).^2)/sum((d(:,iii)-mean(d(:,iii))).^2);
                rsqrd(1,iii)=1 - sum(residual(:,iii).^2)/((length(d(displaced(kk,1):displaced(kk,2),iii))-1)*var(d(:,iii))); %r-squared
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
    
            Vf(kk,:)=[model(2,1)*10 model(2,2)*10 model(2,3)*10];
        
            he=subplot(3,1,1);
            hold on
            plot(t(displaced(kk,1):displaced(kk,2),1),d(displaced(kk,1):displaced(kk,2),1),'o', 'MarkerSize', 3, 'MarkerEdgeColor', '#003399');
            plot(t(displaced(kk,1):displaced(kk,2),1),dhat(:,1)','g-', 'LineWidth', 0.7);
            ylabel('East (cm)');
            title(sitename, 'FontSize', 12);
            Ve=['V_',num2str(kk),'=',num2str(model(2,1)*10,2),' mm/yr'];
            text(mean(t(displaced(kk,1):displaced(kk,2),1))-0.2,mean(d(displaced(kk,1):displaced(kk,2),1))-6.0,Ve,'FontSize',6,'Color','#D95319'); % ADJUST TEXT POSITION -> text(x+-N,y+-N,Ve) where N>=0
            set(0,'defaultAxesFontSize',8);
            set(he,'linewidth',0.9,'box','on');
    
            hn=subplot(3,1,2);
            hold on
            plot(t(displaced(kk,1):displaced(kk,2),1),d(displaced(kk,1):displaced(kk,2),2),'o', 'MarkerSize', 3, 'MarkerEdgeColor', '#003399');
            plot(t(displaced(kk,1):displaced(kk,2),1),dhat(:,2)','g-', 'LineWidth', 0.7);
            ylabel('North (cm)');
            Vn=['V_',num2str(kk),'=',num2str(model(2,2)*10,2),' mm/yr'];
            text(mean(t(displaced(kk,1):displaced(kk,2),1))+0.7,mean(d(displaced(kk,1):displaced(kk,2),2))-1.0,Vn,'FontSize',6,'Color','#D95319'); % ADJUST TEXT POSITION -> text(x+-N,y+-N,Vn) where N>=0
            set(0,'defaultAxesFontSize',8);
            set(hn,'linewidth',0.9,'box','on');
    
            hu=subplot(3,1,3);
            hold on
            plot(t(displaced(kk,1):displaced(kk,2),1),d(displaced(kk,1):displaced(kk,2),3),'o', 'MarkerSize', 3, 'MarkerEdgeColor', '#003399');
            plot(t(displaced(kk,1):displaced(kk,2),1),dhat(:,3)','g-', 'LineWidth', 0.7);
            ylabel('Up (cm)');
            xlabel('TIME');
            Vu=['V_',num2str(kk),'=',num2str(model(2,3)*10,2),' mm/yr'];
            text(mean(t(displaced(kk,1):displaced(kk,2),1)),mean(d(displaced(kk,1):displaced(kk,2),3))-4.0,Vu,'FontSize',6,'Color','#D95319'); % ADJUST TEXT POSITION -> text(x+-N,y+-N,Vu) where N>=0
            set(0,'defaultAxesFontSize',8);
            set(hu,'linewidth',0.9,'box','on');
        end
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