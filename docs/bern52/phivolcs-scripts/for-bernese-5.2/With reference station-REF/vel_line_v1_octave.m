%% plot time series figure and calculate velocity simpally (fitting a straight line)

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
   
    for iii=1:1:3
      model(1:2,iii)= inv(G'*G) * G' * d(:,iii); 	
      dhat(:,iii)=G*model(:,iii);
      residual(:,iii)=d(:,iii)-dhat(:,iii);
    end
    
    varM = inv(G'*G); 
    rnorm=[];sig_m=[];
   
    for jjj=1:1:3
        rnorm(jjj)=(residual(:,jjj)'*residual(:,jjj))/(length(residual)-2);
        sig_m(jjj)=sqrt(varM(2,2)*rnorm(jjj));
    end
    
    fprintf(fiddv,'%s %10.5f +- %4.1f    %10.5f +- %4.1f    %10.5f +- %4.1f\n',files,model(2,1)*10,sig_m(1)*10,model(2,2)*10,sig_m(2)*10,model(2,3)*10,sig_m(3)*10);
    % unit:mm (original data: unit=cm)
    
    figure;
    he=subplot(3,1,1);
    plot(t,d(:,1),'bo',t,dhat(:,1)','g-');ylabel('East (cm)');title(sitename);
    %gtext(['V=' num2str(model(2,1)*10,2) ' cm/yr']);
    legend(['V=' num2str(model(2,1)*10,2) ' mm/yr']);
    set(he,'linewidth',1.2,'box','on','fontsize',12);
    
    hn=subplot(3,1,2);
    plot(t,d(:,2),'bo',t,dhat(:,2)','g-');ylabel('North (cm)');
    %gtext(['V=' num2str(model(2,2)*10,2) ' cm/yr']);
    legend(['V=' num2str(model(2,2)*10,2) ' mm/yr']);
    set(hn,'linewidth',1.2,'box','on','fontsize',12);
    
    hu=subplot(3,1,3);
    plot(t,d(:,3),'bo',t,dhat(:,3)','g-');ylabel('Up (cm)');xlabel('TIME');
    %gtext(['V=' num2str(model(2,3)*10,2) ' cm/yr']);
    legend(['V=' num2str(model(2,3)*10,2) ' mm/yr']);
    set(hu,'linewidth',1.2,'box','on','fontsize',12);
    
    %print('-djpeg','-r300',[sitename '_rmc']);
    print('-djpeg','-r300',[sitename]);
    close all;
    end 
end

fclose(fiddv);