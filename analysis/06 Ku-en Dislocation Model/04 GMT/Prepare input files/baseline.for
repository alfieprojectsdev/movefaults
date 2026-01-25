      program baseline

      implicit none
      character in1*100,in2*100,in3*100,in4*100,ou1*100,ou2*100,ou3*100
      integer i,j,np,stat
      double precision,allocatable::pt(:,:),obs(:),cal(:),res(:)
      
      open(11,'baseline.inp',status='old')
      read(11,'(/,a)')in1
      read(11,'(/,a)')in2
      read(11,'(/,a)')in3
      read(11,'(/,a)')in4
      read(11,'(/,a)')ou1
      read(11,'(/,a)')ou2
      read(11,'(/,a)')ou3
      close(11)
      
      open(11,in1,status='old')
      np=0
      stat=0
      do while(stat==0)
        read(11,*,iostat=stat)
        if(stat/=0) exit
        np=np+1
      end do
      
      allocate(pt(np,4),obs(np),cal(np),res(np))
      rewind(11)
      do i=1,np
        read(11,*)(pt(i,j),j=1,4)
      end do
      close(11)

      open(11,in2,status='old')
      do i=1,np
        read(11,*)obs(i)
      end do
      close(11)

      open(11,in3,status='old')
      do i=1,np
        read(11,*)cal(i)
      end do
      close(11)

      open(11,in4,status='old')
      do i=1,np
        read(11,*)res(i)
      end do
      close(11)
      
      open(11,ou1)
      do i=1,np
        write(11,'("X -Z",f9.4)') obs(i)
        write(11,'(2f8.4)')pt(i,1),pt(i,2)
        write(11,'(2f8.4)')pt(i,3),pt(i,4)
      end do
      close(11)
      open(11,ou2)
      do i=1,np
        write(11,'("X -Z",f9.4)') cal(i)
        write(11,'(2f8.4)')pt(i,1),pt(i,2)
        write(11,'(2f8.4)')pt(i,3),pt(i,4)
      end do
      close(11)
      open(11,ou3)
      do i=1,np
        write(11,'("X -Z",f9.4)') res(i)
        write(11,'(2f8.4)')pt(i,1),pt(i,2)
        write(11,'(2f8.4)')pt(i,3),pt(i,4)
      end do
      close(11)
      
      deallocate(pt,obs,cal,res)
      
      stop
      end
