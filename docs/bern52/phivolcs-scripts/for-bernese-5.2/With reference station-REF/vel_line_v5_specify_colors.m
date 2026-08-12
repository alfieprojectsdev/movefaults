%% plot time series figure and calculate velocity simpally (fitting a straight line)
% modified by Cassandra Cabigan 07/2022
% combining time series plots (specify colors)
% TO CUSTOMIZE (LOOK FOR COMMENTS)

fid=fopen('123','r'); %format SITE 0(if blue)/1(if red)
filename=fscanf(fid,'%s',[5 inf]);
fclose(fid);
filename=filename';
num_file=size(filename,1);

fig=figure;
h=subplot(1,1,1);
ylabel('East (cm)'); %change label (East/North/Up)
xlabel('TIME');
set(0,'defaultAxesFontSize',8);
set(h,'linewidth',0.9,'box','on');
fig.Position(3:4)=[450,550]; %change figure size; remove for default size

for k=1:1:num_file
    
    files=filename(k,1:4);
    rawdata=load(files);
    t=rawdata(:,1);  
    d=rawdata(:,2:4);
    d(:,1)=d(:,1)-mean(d(:,1)); d(:,2)=d(:,2)-mean(d(:,2)); d(:,3)=d(:,3)-mean(d(:,3));
    sitename=files;e=d(:,1);n=d(:,2);u=d(:,3);
    d=d*100;
    N=length(t);
    cv=str2num(filename(k,5));
    
    if cv==0
    hold on
    plot(t,d(:,1)+(k*30),'o', 'MarkerSize', 2,'MarkerEdgeColor','blue'); %change y-axis values -> d(:,?)(1:East;2:North;3:Up)+(k*N)where N>0
    plot(2023,0); %define the extent of x-axis to fit text inside the plot
    text(2022,mean(d(:,1)+(k*30)),sitename,'FontSize',9,'FontWeight','bold','FontAngle','italic','Color','blue'); %specify position of text -> x-axis=time; y-axis=d(:,?)(1:East;2:North;3:Up)+(k*N)where N>0
    hold off
    end
    
    if cv==1
    hold on
    plot(t,d(:,1)+(k*30),'o', 'MarkerSize', 2,'MarkerEdgeColor','red'); %change y-axis values -> d(:,?)(1:East;2:North;3:Up)+(k*N)where N>0
    plot(2023,0); %define the extent of x-axis to fit text inside the plot
    text(2022,mean(d(:,1)+(k*30)),sitename,'FontSize',9,'FontWeight','bold','FontAngle','italic','Color','red'); %specify position of text -> x-axis=time; y-axis=d(:,?)(1:East;2:North;3:Up)+(k*N)where N>0
    hold off
    end
    
end

print(fig,'Hor_E','-djpeg','-r300'); %change filename (Hor_E/Hor_N/Ver_U)

close all