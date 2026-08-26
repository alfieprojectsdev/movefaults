%% plot time series figure and calculate velocity simpally (fitting a straight line)%%
% modified by Cassandra Cabigan 07/2022
% plotting VADASE

close all
clear

fid=fopen('123','r');
filename=fscanf(fid,'%s',[4 inf]); %open files: *NEU
fclose(fid);
filename=filename';
num_file=size(filename,1);


for k=1:1:num_file
    
    files=filename(k,:);
    rawdata=importdata(files);
    t=datenum(rawdata.textdata(:,1),'HH:MM:SS');
    d=rawdata.data(:,1:3);
    sitename=files;e=d(:,1);n=d(:,2);u=d(:,3);
    N=length(t);
   
    figure;
    he=subplot(3,1,1);
    plot(t,d(:,1),'o', 'MarkerSize', 3, 'MarkerEdgeColor', '#003399');
    datetick('x','HH:MM:SS');
    set(0,'defaultAxesFontSize',8);
    ylabel('East (mm/s)');
    title([sitename,'\_LVM'], 'FontSize', 12);
    set(he,'linewidth',0.9,'box','on');
    
    hn=subplot(3,1,2);
    plot(t,d(:,2),'o', 'MarkerSize', 3, 'MarkerEdgeColor', '#003399');
    datetick('x','HH:MM:SS');
    ylabel('North (mm/s)');
    set(0,'defaultAxesFontSize',8);
    set(hn,'linewidth',0.9,'box','on');
    
    hu=subplot(3,1,3);
    plot(t,d(:,3),'o', 'MarkerSize', 3, 'MarkerEdgeColor', '#003399');
    datetick('x','HH:MM:SS');
    ylabel('Up (mm/s)');
    xlabel('Time (Local)');
    set(0,'defaultAxesFontSize',8);
    set(hu,'linewidth',0.9,'box','on');
    
    print('-djpeg','-r300',[sitename]);
    close all;
end