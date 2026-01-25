%% plot time series figure and calculate velocity simpally (fitting a straight line)
%{ 
modified by Cassandra Cabigan 09/2024
make text file with filename "offsets"
format:| sitename | date of displacement | type |
e.g. ALBU 2017.5147 EQ
for type of offset (third column): EQ(earthquake), CE(change of equipment), UK(unknown), VE(volcanic eruption)

Final velocity=velocity calculated after the last discontinuity
 
rmoutliers function using IQR method for outliers detection
(threshold factor set to 3*IQR; default is 1.5*IQR)

compatible with MATLAB R2020b
%}

close all
clear

fid=fopen('123','r');
filename=fscanf(fid,'%s',[4 inf]); %load TNEU
fclose(fid);
filename=filename';
num_file=size(filename,1);

fid0=fopen('offsets','r'); %load offsets (site, date of displacement, type)
offset=textscan(fid0,'%s %f %s');
fclose(fid0);
[offSites, offTime, offType] = offset{:};

%create a velocity output file
outvel=['Velocity_rover(regress)_10'];
fiddv=fopen(outvel,'w');
fprintf(fiddv,'%s\n','-----------------------------------------------------------------------');
fprintf(fiddv,'%s\n','sites        Ve                     Vn                    Vu   unit: mm');
fprintf(fiddv,'%s\n','-----------------------------------------------------------------------');

rem_outliers=['outliers'];
fiddv0=fopen(rem_outliers,'w');
fprintf(fiddv0,'%s\n','------------------');
fprintf(fiddv0,'%s\n','outliers list');
fprintf(fiddv0,'%s','------------------');

fig=figure;

%iterate over sites
for k=1:1:num_file
    files=filename(k,:);
    rawdata=load(files);
    d=rawdata(:,1:4);
    d(:,2)=d(:,2)-mean(d(:,2)); d(:,3)=d(:,3)-mean(d(:,3)); d(:,4)=d(:,4)-mean(d(:,4));
    sitename=files(1:4);
    d(:,2:4)=d(:,2:4)*100;  %m--> cm
    Nn=length(d(:,1));
    Vf=[];
    
    %locate the offsets
    offSI=find(contains(offSites,sitename));
    offN=length(offSI);
    O=[1];
    T_eq=[];
    T_ce=[];
    T_uk=[];
    T_ve=[];
    P=[];
    
    %add sitename to outliers file
    fprintf(fiddv0,'\n%s\n',files);
    
    for j=1:1:offN
        k=offSI(j);
        Tdiff=d(:,1)-offTime(k,1);
        offTI=min(find(Tdiff>=0));
        O=[O; offTI];
        P=[P; offTI-1];
        offTt=offTime(k,1);
        if strcmp(offType(k,1),'EQ')
            T_eq=[T_eq; offTt];
        elseif strcmp(offType(k,1),'CE')
            T_ce=[T_ce; offTt];
        elseif strcmp(offType(k,1),'VE')
            T_ve=[T_ve; offTt];
        elseif strcmp(offType(k,1),'UK')
            T_uk=[T_uk; offTt];
        end
    end
    P=[P; Nn];
    O=[O, P];
    rem_t=[];
    
    %calculating velocities and errors
    for kk=1:1:offN+1
        residual=[];
        dhat=[];
        model=[];
        rsqrd=[];
        
        for N=length(O(kk,1):O(kk,2))
            G=zeros(N,2);
            G(:,1)=ones(N,1);
            G(:,2)=d(O(kk,1):O(kk,2),1);
        end
        
        %detecting and removing outliers
        [cleaned_d,cleaned_i]=rmoutliers(d(O(kk,1):O(kk,2),:),"quartiles",'ThresholdFactor',3);
        cleaned_i=find(cleaned_i==1);
        rem_t=G(cleaned_i(:,1),2);
        
        for iii=1:1:3
            model(1:2,iii)= G\d(O(kk,1):O(kk,2),iii+1); %least squares regression
            dhat(:,iii)=G*model(:,iii); %fitted y
            residual(:,iii)=d(O(kk,1):O(kk,2),iii+1)-dhat(:,iii); %residuals
            %rsqrd(1,iii)=1 - sum(residual(:,iii).^2)/sum((d(:,iii)-mean(d(:,iii))).^2);
            rsqrd(1,iii)=1 - sum(residual(:,iii).^2)/((length(d(O(kk,1):O(kk,2),iii+1))-1)*var(d(:,iii+1))); %r-squared
        end

        %varM = inv(G'*G);
        rnorm=[];sig_m=[];stt=[];rstd=[];

        for jjj=1:1:3
            rnorm(1,jjj)=sum(residual(:,jjj).^2)/(length(residual)-2);
            stt=sum((G(:,2)-mean(G(:,2))).^2);
            %sig_m(jjj)=sqrt(varM(2,2)*rnorm(jjj)); %in cm, standard error of a regression slope
            sig_m(1,jjj)=sqrt(rnorm(jjj)/stt); %in cm, standard error of a regression slope
            rstd(1,jjj)=sqrt(rnorm(jjj)); %in cm, residual std or standard error of the estimate
        end
        
        %add velocities to output file
        fprintf(fiddv,'%s %10.5f +- %4.1f    %10.5f +- %4.1f    %10.5f +- %4.1f\n',files,model(2,1)*10,sig_m(1)*10,model(2,2)*10,sig_m(2)*10,model(2,3)*10,sig_m(3)*10);
        % unit:mm (original data: unit=cm)
        
        %value of final vel
        Vf(kk,:)=[model(2,1)*10 model(2,2)*10 model(2,3)*10];
        
        %add outliers to output file
        fprintf(fiddv0,'%4.4f\n',rem_t);
        
        %generating time series plots
        he=subplot(3,1,1);
        hold on
        plot(d(O(kk,1):O(kk,2),1),d(O(kk,1):O(kk,2),2),'o', 'MarkerSize', 3, 'MarkerEdgeColor', '#003399');
        plot(d(O(kk,1):O(kk,2),1),dhat(:,1)','g-', 'LineWidth', 0.7);
        ylabel('East (cm)');
        title(sitename, 'FontSize', 12);
        set(0,'defaultAxesFontSize',8);
        set(he,'linewidth',0.9,'box','on');
        time_vectors = {T_eq, T_ce, T_ve, T_uk};
        colors = {'#D95319', '#0072BD', '#EDB120', 'k'};
        for i = 1:length(time_vectors)
            if ~isempty(time_vectors{i})
            h=arrayfun(@(a)xline(a, 'linewidth', 0.2, 'linestyle', '--', 'color', colors{i}),time_vectors{i});
            end
        end
        
        hn=subplot(3,1,2);
        hold on
        plot(d(O(kk,1):O(kk,2),1),d(O(kk,1):O(kk,2),3),'o', 'MarkerSize', 3, 'MarkerEdgeColor', '#003399');
        plot(d(O(kk,1):O(kk,2),1),dhat(:,2)','g-', 'LineWidth', 0.7);
        ylabel('North (cm)');
        set(0,'defaultAxesFontSize',8);
        set(hn,'linewidth',0.9,'box','on');
        time_vectors = {T_eq, T_ce, T_ve, T_uk};
        colors = {'#D95319', '#0072BD', '#EDB120', 'k'};
        for i = 1:length(time_vectors)
            if ~isempty(time_vectors{i})
            h=arrayfun(@(a)xline(a, 'linewidth', 0.2, 'linestyle', '--', 'color', colors{i}),time_vectors{i});
            end
        end

        hu=subplot(3,1,3);
        hold on
        plot(d(O(kk,1):O(kk,2),1),d(O(kk,1):O(kk,2),4),'o', 'MarkerSize', 3, 'MarkerEdgeColor', '#003399');
        plot(d(O(kk,1):O(kk,2),1),dhat(:,3)','g-', 'LineWidth', 0.7);
        ylabel('Up (cm)');
        xlabel('TIME');
        set(0,'defaultAxesFontSize',8);
        set(hu,'linewidth',0.9,'box','on');
        time_vectors = {T_eq, T_ce, T_ve, T_uk};
        colors = {'#D95319', '#0072BD', '#EDB120', 'k'};
        for i = 1:length(time_vectors)
            if ~isempty(time_vectors{i})
            h=arrayfun(@(a)xline(a, 'linewidth', 0.2, 'linestyle', '--', 'color', colors{i}),time_vectors{i});
            end
        end
    end

    he=subplot(3,1,1);
    Vef=['V=',num2str(round(Vf(end,1))),' mm/yr'];
    annotation('textbox',[0.76 0.87 0.135 0.035],'String',Vef,'FontSize',7, 'BackgroundColor','white','FaceAlpha',0.8, 'Margin',3);
    
    hn=subplot(3,1,2);
    Vnf=['V=',num2str(round(Vf(end,2))),' mm/yr'];
    annotation('textbox',[0.76 0.57 0.135 0.035],'String',Vnf,'FontSize',7, 'BackgroundColor','white','FaceAlpha',0.8, 'Margin',3);
    
    hu=subplot(3,1,3);
    Vuf=['V=',num2str(round(Vf(end,3))),' mm/yr'];
    annotation('textbox',[0.76 0.27 0.135 0.035],'String',Vuf,'FontSize',7, 'BackgroundColor','white','FaceAlpha',0.8, 'Margin',3);
    
    %adding details to plots
    ndt=num2str(min(d(:,1)));
    mdt=num2str(max(d(:,1)));
    Mt=strlength(mdt);
    Nt=strlength(ndt);
    mdt=[mdt(1:4),' ',num2str(round(str2num(mdt(5:Mt))*365.25))];
    ndt=[ndt(1:4),' ',num2str(round(str2num(ndt(5:Nt))*365.25))];
    ltm=['Observation (yyyy doy): ' num2str(ndt) ' - ' num2str(mdt)];
    annotation('textbox',[0.13 0.0001 0.5 0.04],'String',ltm,'EdgeColor','none','FontSize',5);
    
    datenow=datetime('now');
    dn=['Plotted on ' datestr(datenow) ' by MOVE Faults'];
    annotation('textbox',[0.57 0.0001 0.5 0.04],'String',dn,'EdgeColor','none','FontSize',5);

print('-djpeg','-r300',[sitename]);
close all;

end

fclose(fiddv);
fclose(fiddv0);