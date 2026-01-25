%% plot time series figure
% modified by Cassandra Cabigan 09/2022
% plotting kinematic
% time must be in this format -> yyyy-mm-dd HH:MM:SS

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
    t=datenum(rawdata.textdata(:,1),'yyyy-mm-dd HH:MM:SS');
    d=rawdata.data(:,1:3);
    d(:,1)=d(:,1)-mean(d(:,1)); d(:,2)=d(:,2)-mean(d(:,2)); d(:,3)=d(:,3)-mean(d(:,3));
    sitename=files;e=d(:,1);n=d(:,2);u=d(:,3);
	d=d*100;  %m--> cm
    N=length(t);
    eq=datenum('2022-07-27 00:43:24');
   
    figure;
    he=subplot(3,1,1);
    plot(t,d(:,1),'-', 'LineWidth', 1, 'Color', '#003399');
    xline(eq,'-r','event', 'LineWidth', 1, 'FontSize', 6);
    datetick('x','yyyy-mm-dd HH:MM:SS');
    title([sitename,'\_KIN'], 'FontSize', 12);
    ylabel('East (cm)');
    he.XAxis.FontSize=7;
    he.YAxis.FontSize=7;
    grid minor;
    set(he,'linewidth',0.9,'box','on');
    
    hn=subplot(3,1,2);
    plot(t,d(:,2),'-', 'LineWidth', 1, 'Color', '#003399');
    xline(eq,'-r','event', 'LineWidth', 1, 'FontSize', 6);
    datetick('x','yyyy-mm-dd HH:MM:SS');
    ylabel('North (cm)');
    hn.XAxis.FontSize=7;
    hn.YAxis.FontSize=7;
    grid minor;
    set(hn,'linewidth',0.9,'box','on');
    
    hu=subplot(3,1,3);
    plot(t,d(:,3),'-', 'LineWidth', 1, 'Color', '#003399');
    xline(eq,'-r','event', 'LineWidth', 1, 'FontSize', 6);
    datetick('x','yyyy-mm-dd HH:MM:SS');
    ylabel('Up (cm)');
    hu.XAxis.FontSize=7;
    hu.YAxis.FontSize=7;
    grid minor;
    xlabel('Time (UTC)');
    set(hu,'linewidth',0.9,'box','on');
    
    %print('-djpeg','-r300',[sitename '_rmc']);
    print('-djpeg','-r300',[sitename]);
    close all;
end