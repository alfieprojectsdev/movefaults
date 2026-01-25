      program fault

      implicit none
      character in1*100,in2*100,in3*100,in4*100,in5*100,in6*100
      character ou1*100,ou2*100,ou3*100,ou4*100,ou5*100,ou6*100
      integer i,j,nhe,nve,n
      double precision,allocatable::x(:,:),y(:,:),z(:,:),s(:,:),ns(:)
      double precision,allocatable::dp(:),str(:),az(:)
      double precision,allocatable::len_o(:),wid_o(:),len(:,:),wid(:,:)
      real*8 pi,xdt,ydt,ox,oy,cx,cy,m0,dummy
      
      pi=atan(1.)*4
      ydt=111.325

      open(11,'fault.inp',status='old')
      read(11,'(/,a)')in1
      read(11,'(/,a)')in2
      read(11,'(/,a)')in3
      read(11,'(/,a)')in4
      read(11,'(/,a)')in5
      read(11,'(/,a)')in6
      read(11,'(/,a)')ou1
      read(11,'(/,a)')ou2
      read(11,'(/,a)')ou3
      read(11,'(/,a)')ou4
      read(11,'(/,a)')ou5
      read(11,'(/,a)')ou6
      close(11)
      
      open(11,in1,status='old')
      read(11,*)ox,oy
      read(11,*)nhe
      read(11,*)nve
      close(11)
      
      allocate(x(nhe*nve,4),y(nhe*nve,4),z(nhe*nve,4),s(nhe*nve,4))
      allocate(dp(nhe*nve),str(nhe*nve),len_o(nhe*nve),wid_o(nhe*nve))
      allocate(len(nhe,nve),wid(nhe,nve),az(nhe*nve),ns(nhe*nve))
      
      open(11,in2,status='old')
      do i=1,nhe*nve
        read(11,*)len_o(i),wid_o(i),dummy,dp(i),str(i)
        str(i)=str(i)-90
      end do
      close(11)
      n=0
      do i=1,nhe
        do j=1,nve
          n=n+1
          len(i,j)=len_o(n)
          wid(i,j)=wid_o(n)
        end do
      end do

      open(11,in3,status='old')
      do i=1,nhe*nve
        read(11,*)(x(i,j),j=1,4)
      end do
      close(11)
      open(11,in4,status='old')
      do i=1,nhe*nve
        read(11,*)(y(i,j),j=1,4)
      end do
      close(11)
      open(11,in5,status='old')
      do i=1,nhe*nve
        read(11,*)(z(i,j),j=1,4)
      end do
      close(11)
      open(11,in6,status='old')
      do i=1,nhe*nve
        read(11,*)(s(i,j),j=1,3)
        if(s(i,1)==0.d0.and.s(i,2)==0.d0) then
          az(i)=0.+str(i)
        else
          az(i)=atan2(s(i,1),(s(i,2)*cos(dp(i)*pi/180.)))*180/pi+str(i)
        end if
        ns(i)=sqrt(s(i,1)**2+(s(i,2)*cos(dp(i)*pi/180.))**2)
      end do
      close(11)
      
      
      open(11,ou1)
      open(12,ou2)
      do i=1,nhe
        do j=1,nve
          write(11,'("X -Z",f11.4)')s((i-1)*nve+j,3)
          write(11,'(2f11.4)')(i-1)*len(i,j),wid(i,j)
          write(11,'(2f11.4)')i*len(i,j),wid(i,j)
          write(11,'(2f11.4)')i*len(i,j),wid(i,j)
          write(11,'(2f11.4)')(i-1)*len(i,j),wid(i,j)
          write(12,'(4f11.4," 0 0 0")')(2*i-1)/2.*len(i,j),wid(i,j)/2.,
     +    s((i-1)*nve+j,1),-s((i-1)*nve+j,2)
        end do
      end do
      close(11)
      close(12)
      
      open(11,ou3)
      do i=1,nhe*nve
        write(11,'("X -Z",f11.4)')s(i,3)
        do j=1,4
          write(11,'(3f11.4)')x(i,j),y(i,j),-z(i,j)
        end do
      end do
      close(11)
      
      open(11,ou4)
      open(12,ou5)
      xdt=cos(oy*pi/180.)*ydt
      do i=1,nhe*nve
        write(11,'("X -Z",f11.4)')s(i,3)
        cx=0.
        cy=0.
        do j=1,4
          x(i,j)=x(i,j)/xdt+ox
          y(i,j)=y(i,j)/ydt+oy
          cx=cx+x(i,j)
          cy=cy+y(i,j)
          write(11,'(2f9.5)')x(i,j),y(i,j)
        end do
        cx=cx/4.
        cy=cy/4.
        write(12,'(2f9.5,2f9.2," 0 0 0")')cx,cy,
     +  ns(i)*sin(az(i)*pi/180.),ns(i)*cos(az(i)*pi/180.)
      end do
      close(11)
      close(12)
      
      open(11,ou6)
      m0=0.d0
      do i=1,nhe*nve
        m0=m0+3.0e23*len_o(i)*wid_o(i)*s(i,3)/1000.
      end do
      write(11,'("moment = ",e9.3," dyne-cm")')m0
      write(11,'("Mw = ",f4.2)')2./3.*log10(m0)-10.7
      close(11)
      
      deallocate(x,y,z,s,dp,str,len_o,wid_o,len,wid,az,ns)
      
      stop
      end
