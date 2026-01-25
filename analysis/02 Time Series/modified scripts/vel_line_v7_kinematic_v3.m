%% plot time series figure
% modified by Cassandra Cabigan 09/2022
% plotting kinematic
% time must be in this format -> yyyy-MM-dd HH:mm:ss
% UT to PHT (UTC+8)
% LOOK FOR COMMENTS (ALL CAPS)

close all
clear

fid=fopen('123','r');
filename=fscanf(fid,'%s',[4 inf]); %open files: *NEU
fclose(fid);
filename=filename';
num_file=size(filename,1);


for k=1:1:num_file
    
    files=filename(k,:);
    delimiterIn=',';
    rawdata=importdata(files,delimiterIn);
    t=datetime(rawdata.textdata(:,1),'InputFormat','yyyy-MM-dd HH:mm:ss','TimeZone','UTC');
    t.TimeZone= '+08:00';
    % t.Format='yyyy-MM-dd HH:mm:ss';
    d=rawdata.data(:,1:3);
    d(:,1)=d(:,1)-mean(d(:,1)); d(:,2)=d(:,2)-mean(d(:,2)); d(:,3)=d(:,3)-mean(d(:,3));
    sitename=files;e=d(:,1);n=d(:,2);u=d(:,3);
	d=d*100;  %m--> cm
    N=length(t);
    eq=datetime('2022-07-27 00:43:24','InputFormat','yyyy-MM-dd HH:mm:ss','TimeZone','UTC'); %EDIT THIS
    eq.TimeZone= '+08:00';
    % eq.Format='yyyy-MM-dd HH:mm:ss';
    
    figure;
    he=subplot(3,1,1);
    plot(t,d(:,1),'-', 'LineWidth', 1, 'Color', '#003399');
    xline(eq,'-r', 'event', 'LineWidth', 1, 'FontSize', 6);
    datetick('x','HH:MM'); %IF MORE THAN 24 HRS, MAKE HH:MM:SS to HH:MM
    title([sitename,'\_KIN'], 'FontSize', 12);
    % subtitle('Kinematic coordinates every 30 seconds epoch', 'FontSize',7);
    ylabel('East (cm)');
    % set(gca,'XTickLabelRotation',60);
    he.XAxis.FontSize=7;
    he.YAxis.FontSize=7;
    grid minor;
    set(he,'linewidth',0.9,'box','on');
    
    hn=subplot(3,1,2);
    plot(t,d(:,2),'-', 'LineWidth', 1, 'Color', '#003399');
    xline(eq,'-r','event', 'LineWidth', 1, 'FontSize', 6);
    datetick('x','HH:MM'); %IF MORE THAN 24 HRS, MAKE HH:MM:SS to HH:MM
    ylabel('North (cm)');
    % set(gca,'XTickLabelRotation',60);
    hn.XAxis.FontSize=7;
    hn.YAxis.FontSize=7;
    grid minor;
    set(hn,'linewidth',0.9,'box','on');
    
    hu=subplot(3,1,3);
    plot(t,d(:,3),'-', 'LineWidth', 1, 'Color', '#003399');
    xline(eq,'-r', 'event', 'LineWidth', 1, 'FontSize', 6);
    datetick('x','HH:MM'); %IF MORE THAN 24 HRS, MAKE HH:MM:SS to HH:MM
    ylabel('Up (cm)');
    hu.XAxis.FontSize=7;
    hu.YAxis.FontSize=7;
    grid minor;
    xlabel('Time (PHT) of DOY 207-208'); %EDIT THIS
    % set(gca,'XTickLabelRotation',60);
    set(hu,'linewidth',0.9,'box','on');
    
    print('-djpeg','-r300',[sitename]);
    close all;
end